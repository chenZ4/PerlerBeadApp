import SwiftUI
import AppKit

// ============================================================================
// ColorChartView.swift — 编辑式色样册（T6 重绘；保留原 engine 请求/搜索/复制行为）
// ============================================================================

struct ColorChartView: View {
    let paletteInternal: String
    let paletteDisplay: String
    let engine: Engine?
    @Environment(\.dismiss) private var dismiss

    @State private var colors: [[String: Any]] = []
    @State private var filter = ""
    @State private var groups: [String: [[String: Any]]] = [:]
    @State private var copiedCode: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            DoubleRule()
            GeometryReader { geo in
                ScrollView(.vertical, showsIndicators: true) {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        ForEach(Array(groups.keys).sorted(), id: \.self) { group in
                            let items = groups[group] ?? []
                            VStack(alignment: .leading, spacing: 9) {
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text(group)
                                        .font(TFont.didot(20))
                                        .foregroundStyle(Tok.accent)
                                    MicroLabel("GROUP")
                                    Spacer()
                                    Text("\(items.count) 色")
                                        .font(TFont.menlo(9.5))
                                        .foregroundStyle(Tok.inkMuted)
                                }
                                Hairline()
                                LazyVGrid(columns: columns(for: geo.size.width), spacing: 10) {
                                    ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                                        ColorCardView(item: item) { code, name in
                                            copiedCode = code
                                            copyToPasteboard(item: item)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .padding(24)
                }
            }
            Hairline()
            footer
        }
        .frame(width: 1180, height: 760)
        .background(Tok.paper)
        .foregroundStyle(Tok.ink)
        .onAppear(perform: load)
        .onChange(of: filter) { _, _ in regroup() }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                MicroLabel("PALETTE  ·  \(paletteInternal.uppercased())")
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(paletteDisplay).font(TFont.songtiBold(24))
                        .foregroundStyle(Tok.ink)
                    MicroLabelCN("色卡")
                    Text("点击色卡复制色号")
                        .font(TFont.pingfang(10.5)).foregroundStyle(Tok.inkMuted)
                }
            }
            Spacer()
            EditorialField(placeholder: "搜索色号 / 名称 / HEX", text: $filter, width: 240, mono: false)
            Button("关闭") { dismiss() }
                .buttonStyle(GhostButtonStyle(height: 28))
                .keyboardShortcut(.cancelAction)
        }
        .padding(.horizontal, 24)
        .frame(height: 76)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            StatusDot(color: copiedCode == nil ? Tok.success : Tok.accent)
            if let copied = copiedCode {
                Text("已复制 \(copied)").font(TFont.pingfang(10)).foregroundStyle(Tok.accent)
            } else {
                Text("显示 \(filteredCount) / \(colors.count) 色")
                    .font(TFont.pingfang(10)).foregroundStyle(Tok.inkSoft)
            }
            Spacer()
            Text("色号 + 名称 + HEX · 支持搜索 · ESC 关闭")
                .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
        }
        .padding(.horizontal, 24)
        .frame(height: 40)
    }

    private var filteredCount: Int {
        groups.values.reduce(0) { $0 + $1.count }
    }

    private func columns(for width: CGFloat) -> [GridItem] {
        let count = max(5, min(9, Int((width - 48) / 124)))
        return Array(repeating: GridItem(.flexible(), spacing: 10), count: count)
    }

    private func copyToPasteboard(item: [String: Any]) {
        let code = item["code"] as? String ?? ""
        let name = item["name"] as? String ?? ""
        let rgb = item["rgb"] as? [Int] ?? [0, 0, 0]
        let text = "\(code) \(name) | RGB\(rgb)"
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    // MARK: - 数据（沿用原实现）

    private func load() {
        guard let engine else { return }
        engine.request(op: "palette_colors", params: ["internal": paletteInternal]) { result in
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
            let rgb = item["rgb"] as? [Int] ?? []
            let hex = String(format: "#%02x%02x%02x",
                             rgb.count > 0 ? rgb[0] : 0,
                             rgb.count > 1 ? rgb[1] : 0,
                             rgb.count > 2 ? rgb[2] : 0)
            return code.contains(ft) || name.contains(ft) || hex.contains(ft)
        }
        var g: [String: [[String: Any]]] = [:]
        for item in filtered {
            let key = item["group"] as? String ?? "?"
            g[key, default: []].append(item)
        }
        groups = g
    }
}

/// 单张色卡：色块 + 色号 + 名称（编辑式，无圆角/无阴影）
struct ColorCardView: View {
    let item: [String: Any]
    var onCopy: ((String, String) -> Void)? = nil

    var body: some View {
        let rgb = item["rgb"] as? [Int] ?? [0, 0, 0]
        let code = item["code"] as? String ?? ""
        let name = item["name"] as? String ?? ""
        VStack(alignment: .leading, spacing: 5) {
            Rectangle()
                .fill(Color(red: Double(rgb[0]) / 255,
                            green: Double(rgb[1]) / 255,
                            blue: Double(rgb[2]) / 255))
                .frame(height: 84)
                .overlay(Rectangle().stroke(Tok.ink.opacity(0.12), lineWidth: 0.8))
                .overlay(alignment: .topLeading) {
                    // 色号标签固定在色块上，用与主题无关的明暗两色保证可读
                    let onLightSwatch = brightness(rgb) > 0.55
                    Text(code)
                        .font(TFont.menloBold(9))
                        .foregroundStyle(onLightSwatch
                                         ? Color(hex: 0x2A2118)
                                         : Color(hex: 0xFBF6EC))
                        .padding(.horizontal, 5).frame(height: 16)
                        .background(onLightSwatch
                                    ? Color(hex: 0xFBF6EC).opacity(0.82)
                                    : Color(hex: 0x17120D).opacity(0.55))
                        .padding(5)
                }
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(code).font(TFont.menloBold(10.5)).foregroundStyle(Tok.ink)
                Text(name).font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            onCopy?(code, name)
        }
        .help("点击复制 \(code) \(name)")
    }

    private func brightness(_ rgb: [Int]) -> Double {
        guard rgb.count >= 3 else { return 0 }
        return (Double(rgb[0]) * 0.299 + Double(rgb[1]) * 0.587
                + Double(rgb[2]) * 0.114) / 255.0
    }
}
