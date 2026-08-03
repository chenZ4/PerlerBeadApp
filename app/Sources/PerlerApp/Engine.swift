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
    private var buffer = ""
    private var pending: [Int: (onProgress: ((Double) -> Void)?,
                                completion: (Result<[String: Any], Error>) -> Void)] = [:]
    private var nextID = 1
    private let syncQueue = DispatchQueue(label: "engine.sync")
    private let readQueue = DispatchQueue(label: "engine.read")
    private let lock = NSLock()
    private var lastError = ""

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

    init?(pythonPath: String) {
        guard FileManager.default.isExecutableFile(atPath: pythonPath) else { return nil }
        process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [Engine.engineScript]
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
        readQueue.async { [weak self] in
            self?.readErrorLoop()
        }
    }

    deinit {
        process.terminate()
    }

    func ping(completion: @escaping (Result<Bool, Error>) -> Void) {
        request(op: "ping", params: [:]) { result in
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
                 timeout: TimeInterval = 30,
                 completion: @escaping (Result<[String: Any], Error>) -> Void) {
        let rid = requestID ?? nextID
        if requestID == nil { nextID += 1 }

        lock.lock()
        pending[rid] = (onProgress, completion)
        lock.unlock()

        // 超时保护：pending 未被消费则报超时
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout) { [weak self] in
            guard let self else { return }
            self.lock.lock()
            let cb = self.pending.removeValue(forKey: rid)?.completion
            self.lock.unlock()
            cb?(.failure(EngineError.timeout))
        }

        var msg: [String: Any] = ["id": rid, "op": op]
        if !params.isEmpty { msg["params"] = params }
        guard let data = try? JSONSerialization.data(withJSONObject: msg),
              let line = String(data: data, encoding: .utf8) else {
            lock.lock()
            pending.removeValue(forKey: rid)
            lock.unlock()
            completion(.failure(EngineError.invalidResponse))
            return
        }
        let handle = inPipe.fileHandleForWriting
        handle.write((line + "\n").data(using: .utf8)!)
    }

    private func readLoop() {
        let handle = outPipe.fileHandleForReading
        while true {
            let data = handle.availableData
            if data.isEmpty { break }
            guard let chunk = String(data: data, encoding: .utf8) else { continue }
            buffer += chunk
            while let nl = buffer.firstIndex(of: "\n") {
                let line = String(buffer[..<nl])
                buffer.removeSubrange(...nl)
                guard !line.isEmpty else { continue }
                handleLine(line)
            }
        }
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
