import Foundation

/// 引擎 JSON 协议客户端（stdio 行协议）
/// 请求:  {"id":1,"op":"...","params":{...}}
/// 响应:  {"id":1,"ok":true,...}
/// 事件:  {"id":1,"event":"progress","progress":0.5}
/// 取消:  {"id":1,"op":"cancel"}
final class Engine {

    enum EngineError: LocalizedError {
        case launchFailed
        case invalidResponse
        case timeout
        case serverError(String)
        var errorDescription: String? {
            switch self {
            case .launchFailed: return "无法启动引擎"
            case .invalidResponse: return "引擎响应无效"
            case .timeout: return "引擎请求超时"
            case .serverError(let m): return m
            }
        }
    }

    private let process: Process
    private let outPipe = Pipe()
    private let inPipe = Pipe()
    private let errPipe = Pipe()
    private var dataBuffer = Data()
    private var pending: [Int: (onProgress: ((Double) -> Void)?,
                                completion: (Result<[String: Any], Error>) -> Void)] = [:]
    private var nextID = 1
    private let readQueue = DispatchQueue(label: "engine.read")
    private let errorQueue = DispatchQueue(label: "engine.error")
    private let lock = NSLock()
    private var lastError = ""
    private var engineExited = false

    /// 引擎进程退出回调（主线程调用）
    var onEngineExit: (() -> Void)?

    static var engineScript: String {
        let dir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return dir.appendingPathComponent("core_server.py").path
    }

    static func findPython() -> String? {
        if let env = ProcessInfo.processInfo.environment["PERLER_PYTHON"], !env.isEmpty {
            return env
        }
        let home = NSHomeDirectory()
        let candidates = [
            "\(home)/miniconda3/envs/pindou/bin/python",
            "\(home)/miniconda3/bin/python",
            "/opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python",
            "/usr/local/miniconda3/envs/pindou/bin/python",
            "/opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python3",
        ]
        for c in candidates where FileManager.default.isExecutableFile(atPath: c) {
            return c
        }
        return nil
    }

    init?(pythonPath: String, scriptPath: String = Engine.engineScript) {
        guard FileManager.default.isExecutableFile(atPath: pythonPath) else { return nil }
        process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath]
        process.standardOutput = outPipe
        process.standardInput = inPipe
        process.standardError = errPipe
        do {
            try process.run()
        } catch {
            return nil
        }
        readQueue.async { [weak self] in
            self?.readLoop()
        }
        // stderr 用独立队列读取：readLoop 阻塞在 stdout 管道上，串行队列会让
        // stderr 永不 drain，管道写满后引擎假死
        errorQueue.async { [weak self] in
            self?.readErrorLoop()
        }
    }

    deinit {
        process.terminate()
    }

    func ping(completion: @escaping (Result<Bool, Error>) -> Void) {
        request(op: "ping", params: [:], timeout: 5) { result in
            switch result {
            case .success(let r):
                completion(.success((r["pong"] as? Bool) ?? false))
            case .failure(let e):
                completion(.failure(e))
            }
        }
    }

    func request(op: String, params: [String: Any],
                 requestID: Int? = nil,
                 onProgress: ((Double) -> Void)? = nil,
                 onStart: ((Int) -> Void)? = nil,
                 timeout: TimeInterval = 15,
                 completion: @escaping (Result<[String: Any], Error>) -> Void) {
        let rid: Int
        if let requestID {
            rid = requestID
        } else {
            lock.lock()
            rid = nextID
            nextID += 1
            lock.unlock()
        }

        // F0: 所有回调强制主线程（@MainActor 状态安全）
        let mainCompletion: (Result<[String: Any], Error>) -> Void = { result in
            DispatchQueue.main.async { completion(result) }
        }
        let mainProgress: ((Double) -> Void)? = onProgress.map { progress in
            { p in DispatchQueue.main.async { progress(p) } }
        }

        if let onStart {
            DispatchQueue.main.async { onStart(rid) }
        }

        lock.lock()
        if engineExited {
            lock.unlock()
            DispatchQueue.main.async {
                completion(.failure(EngineError.serverError("引擎已退出")))
            }
            return
        }
        pending[rid] = (mainProgress, mainCompletion)
        lock.unlock()

        // F3: 超时保护，回调已保证主线程
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout) { [weak self] in
            guard let self else { return }
            self.lock.lock()
            let cb = self.pending.removeValue(forKey: rid)?.completion
            self.lock.unlock()
            DispatchQueue.main.async {
                cb?(.failure(EngineError.timeout))
            }
        }

        var msg: [String: Any] = ["id": rid, "op": op]
        if !params.isEmpty { msg["params"] = params }
        guard let data = try? JSONSerialization.data(withJSONObject: msg),
              let line = String(data: data, encoding: .utf8) else {
            lock.lock()
            pending.removeValue(forKey: rid)
            lock.unlock()
            DispatchQueue.main.async { completion(.failure(EngineError.invalidResponse)) }
            return
        }
        // F2: write 异常防护（引擎退出/pipe 损坏时快速失败而非静默）
        do {
            try inPipe.fileHandleForWriting.write(contentsOf: (line + "\n").data(using: .utf8)!)
        } catch {
            lock.lock()
            let cb = pending.removeValue(forKey: rid)?.completion
            lock.unlock()
            DispatchQueue.main.async {
                cb?(.failure(EngineError.serverError("引擎通信失败：\(error.localizedDescription)")))
            }
        }
    }

    /// 取消指定请求：发送 cancel 指令并移除 pending 条目（晚到的结果/事件被忽略）
    func cancel(requestID: Int) {
        lock.lock()
        pending.removeValue(forKey: requestID)
        lock.unlock()
        guard let data = try? JSONSerialization.data(withJSONObject: ["id": requestID, "op": "cancel"]),
              let line = String(data: data, encoding: .utf8) else { return }
        try? inPipe.fileHandleForWriting.write(contentsOf: (line + "\n").data(using: .utf8)!)
    }

    private func readLoop() {
        let handle = outPipe.fileHandleForReading
        while true {
            let data = handle.availableData
            if data.isEmpty { break }
            // 先按字节累积再按 \n 切行，最后整行解码 UTF-8：
            // 逐块解码会在多字节字符跨块时丢字节，导致含中文的响应被静默吞掉
            dataBuffer.append(data)
            while let nl = dataBuffer.firstIndex(of: 0x0A) {
                let lineData = dataBuffer[..<nl]
                dataBuffer.removeSubrange(...nl)
                guard let line = String(data: lineData, encoding: .utf8), !line.isEmpty else { continue }
                handleLine(line)
            }
        }
        if !dataBuffer.isEmpty {
            if let line = String(data: dataBuffer, encoding: .utf8), !line.isEmpty {
                handleLine(line)
            }
            dataBuffer.removeAll(keepingCapacity: false)
        }
        // F1: 引擎进程退出（EOF）→ 全部 pending 快速失败 + 退出回调
        failAllPending(EngineError.serverError("引擎已退出"))
        DispatchQueue.main.async { [weak self] in
            self?.onEngineExit?()
        }
    }

    /// F1: 引擎退出时让所有挂起请求快速失败
    private func failAllPending(_ error: Error) {
        lock.lock()
        let entries = pending
        pending.removeAll()
        engineExited = true
        lock.unlock()
        for entry in entries.values {
            DispatchQueue.main.async {
                entry.completion(.failure(error))
            }
        }
    }

    /// 供测试使用：强制终止引擎进程
    func terminateForTesting() {
        lock.lock()
        engineExited = true
        lock.unlock()
        process.terminate()
    }

    private func readErrorLoop() {
        let handle = errPipe.fileHandleForReading
        while true {
            let data = handle.availableData
            if data.isEmpty { break }
            if let chunk = String(data: data, encoding: .utf8) {
                lock.lock()
                lastError = String((lastError + chunk).suffix(4096))
                lock.unlock()
            }
        }
    }

    var engineErrorLog: String {
        lock.lock()
        defer { lock.unlock() }
        return lastError
    }

    private func handleLine(_ line: String) {
        guard let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rid = obj["id"] as? Int else { return }

        if let event = obj["event"] as? String, event == "progress",
           let progress = obj["progress"] as? Double {
            lock.lock()
            let cb = pending[rid]?.onProgress
            lock.unlock()
            cb?(progress)
            return
        }

        lock.lock()
        let entry = pending.removeValue(forKey: rid)
        lock.unlock()
        guard let entry else { return }
        if obj["ok"] as? Bool == true {
            entry.completion(.success(obj))
        } else {
            let err = (obj["error"] as? String) ?? "未知错误"
            entry.completion(.failure(EngineError.serverError(err)))
        }
    }
}
