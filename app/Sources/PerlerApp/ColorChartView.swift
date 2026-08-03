import SwiftUI
import AppKit

/// 色卡预览窗口（毛玻璃 + 分组网格）
struct ColorChartView: View {
    let paletteName: String
    let engine: Engine?
    @Environment(\.dismiss) private var dismiss

    @State private var colors: [[String: Any]] = []
    @State private var filter = ""
    @State private var groups: [String: [[String: Any]]] = [:]

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(groups.keys).sorted(), id: \.self) { group in
                        let items = groups[group] ?? []
                        VStack(alignment: .leading, spacing: 6) {
                            Text("【\(group)组】\(items.count) 色")
                                .font(.headline)
                            LazyVGrid(columns: Array(repeating: GridItem(.flexible()),
                                                     count: 7), spacing: 6) {
                                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                                    ColorCardView(item: item)
                                }
                            }
                        }
                        .padding(10)
                        .background(.regularMaterial,
                                    in: RoundedRectangle(cornerRadius: 12))
                    }
                }
                .padding(12)
            }
            .background(Color.gray.opacity(0.06))
        }
        .frame(width: 1000, height: 720)
        .onAppear(perform: load)
    }

    private var header: some View {
        HStack {
            Text("🎨 \(paletteName)")
                .font(.title2.bold())
            Spacer()
            TextField("搜索色号/名称/HEX", text: $filter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
                .onChange(of: filter) { _, _ in regroup() }
            Button("关闭") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(14)
        .background(.ultraThinMaterial)
    }
}

/// 单张色卡卡片
struct ColorCardView: View {
    let item: [String: Any]

    var body: some View {
        let rgb = item["rgb"] as? [Int] ?? [0, 0, 0]
        let code = item["code"] as? String ?? ""
        let name = item["name"] as? String ?? ""
        VStack(alignment: .leading, spacing: 2) {
            RoundedRectangle(cornerRadius: 6)
                .fill(Color(red: Double(rgb[0]) / 255,
                            green: Double(rgb[1]) / 255,
                            blue: Double(rgb[2]) / 255))
                .frame(height: 56)
                .overlay(
                    Text(code)
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(brightness(rgb) > 0.5 ? Color.black : Color.white)
                )
            Text(code)
                .font(.system(size: 11, weight: .bold, design: .monospaced))
            Text(name)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(6)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .onTapGesture {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString("\(code) \(name) | RGB\(rgb)",
                                           forType: .string)
        }
    }

    private func brightness(_ rgb: [Int]) -> Double {
        guard rgb.count >= 3 else { return 0 }
        return (Double(rgb[0]) * 0.299 + Double(rgb[1]) * 0.587
                + Double(rgb[2]) * 0.114) / 255.0
    }
}

// MARK: - 主视图逻辑
extension ColorChartView {
    private func load() {
        guard let engine else { return }
        engine.request(op: "palette_colors", params: ["internal": paletteName]) { result in
            if case .success(let r) = result {
                let codes = r["codes"] as? [String] ?? []
                let names = r["names"] as? [String] ?? []
                let rgbs = r["colors"] as? [[Int]] ?? []
                var items: [[String: Any]] = []
                for i in 0..<min(codes.count, min(names.count, rgbs.count)) {
                    items.append(["code": codes[i], "name": names[i],
                                  "rgb": rgbs[i], "group": String(codes[i].prefix(1))])
                }
                colors = items
                regroup()
            }
        }
    }

    private func regroup() {
        let ft = filter.trimmingCharacters(in: .whitespaces).lowercased()
        let filtered = ft.isEmpty ? colors : colors.filter { item in
            let code = (item["code"] as? String ?? "").lowercased()
            let name = (item["name"] as? String ?? "").lowercased()
            return code.contains(ft) || name.contains(ft)
        }
        var g: [String: [[String: Any]]] = [:]
        for item in filtered {
            let key = item["group"] as? String ?? "?"
            g[key, default: []].append(item)
        }
        groups = g
    }
}
