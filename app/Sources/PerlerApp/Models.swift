import Foundation

struct GenerateResult: Decodable {
    let chartPath: String
    let chartSize: [Int]
    let finishedPath: String?
    let finishedSize: [Int]?
    let colorStats: [String: ColorStat]
    let totalBeads: Int
    let gridW: Int
    let gridH: Int
    let cellSize: Int
    let palette: String
    let cancelled: Bool?
    /// 引擎的非致命提示（chibi 无人脸/几何特效改写网格/参数被钳制/未知特效…）
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case chartPath = "chart_path"
        case chartSize = "chart_size"
        case finishedPath = "finished_path"
        case finishedSize = "finished_size"
        case colorStats = "color_stats"
        case totalBeads = "total_beads"
        case gridW = "grid_w"
        case gridH = "grid_h"
        case cellSize = "cell_size"
        case palette, cancelled, warnings
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        chartPath = try c.decode(String.self, forKey: .chartPath)
        chartSize = try c.decode([Int].self, forKey: .chartSize)
        finishedPath = try c.decodeIfPresent(String.self, forKey: .finishedPath)
        finishedSize = try c.decodeIfPresent([Int].self, forKey: .finishedSize)
        colorStats = try c.decodeIfPresent([String: ColorStat].self, forKey: .colorStats) ?? [:]
        totalBeads = try c.decodeIfPresent(Int.self, forKey: .totalBeads) ?? 0
        gridW = try c.decodeIfPresent(Int.self, forKey: .gridW) ?? 0
        gridH = try c.decodeIfPresent(Int.self, forKey: .gridH) ?? 0
        cellSize = try c.decodeIfPresent(Int.self, forKey: .cellSize) ?? 0
        palette = try c.decodeIfPresent(String.self, forKey: .palette) ?? ""
        cancelled = try c.decodeIfPresent(Bool.self, forKey: .cancelled)
        warnings = try c.decodeIfPresent([String].self, forKey: .warnings) ?? []
    }
}

struct ColorStat: Decodable {
    let rgb: [Int]
    let name: String
    let code: String
    let count: Int

    enum CodingKeys: String, CodingKey { case rgb, name, code, count }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        rgb = try c.decodeIfPresent([Int].self, forKey: .rgb) ?? [0, 0, 0]
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        code = try c.decodeIfPresent(String.self, forKey: .code) ?? ""
        count = try c.decodeIfPresent(Int.self, forKey: .count) ?? 0
    }
}

struct PaletteInfo {
    let display: String
    let internalName: String
    let count: Int

    init(display: String, count: Int, internalName: String) {
        self.display = display
        self.count = count
        self.internalName = internalName
    }
}

struct TemplateInfo {
    let id: String
    let name: String
    let width: Int
    let height: Int
}

extension GenerateResult {
    /// 把 colorStats 转为 JSONSerialization 可序列化的 [String: Any]
    var colorStatsAny: [String: Any] {
        colorStats.mapValues { s in
            ["rgb": s.rgb, "name": s.name, "code": s.code, "count": s.count]
                as [String: Any]
        }
    }
}
