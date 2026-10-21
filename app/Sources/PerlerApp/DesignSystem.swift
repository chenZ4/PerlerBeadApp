import SwiftUI
import AppKit

// ============================================================================
// DesignSystem.swift — 「克制的高级杂志感」设计系统
// 来源：qa/ui/audit.md §3.4（tokens 与 mockup 同源；对比度实测见文档）
// 参考：open-design editorial typography、Monocle 风格档、Kinfolk、Radix Colors、
//       Apple HIG（详见 audit.md §3.2，均为方法论参考，无第三方代码/资源依赖）
// ============================================================================

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255.0,
                  green: Double((hex >> 8) & 0xFF) / 255.0,
                  blue: Double(hex & 0xFF) / 255.0,
                  opacity: opacity)
    }

    init(hexString: String, opacity: Double = 1) {
        let s = hexString.replacingOccurrences(of: "#", with: "")
        self.init(hex: UInt32(s, radix: 16) ?? 0x999999, opacity: opacity)
    }

    /// 随系统外观自动切换的语义色
    static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            let v = isDark ? dark : light
            return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255.0,
                           green: CGFloat((v >> 8) & 0xFF) / 255.0,
                           blue: CGFloat(v & 0xFF) / 255.0,
                           alpha: 1.0)
        })
    }
}

enum Tok {
    // Color —— 纸白/墨黑/米色 + 单一朱砂（亮/暗成对）
    static let paper        = Color.dynamic(light: 0xFAF7F1, dark: 0x14120E)
    static let paperDeep    = Color.dynamic(light: 0xF1EBE1, dark: 0x1C1915)
    static let paperMat     = Color.dynamic(light: 0xFFFFFF, dark: 0x24201A)
    static let ink          = Color.dynamic(light: 0x17140F, dark: 0xF4EFE5)
    static let inkSoft      = Color.dynamic(light: 0x494338, dark: 0xC9C1B2)
    static let inkMuted     = Color.dynamic(light: 0x6F6657, dark: 0xA79E8E)
    static let inkFaint     = Color.dynamic(light: 0x8A8172, dark: 0x7D7466)
    static let hairline     = Color.dynamic(light: 0xD9CFC0, dark: 0x332E27)
    static let hairlineSoft = Color.dynamic(light: 0xE8E1D5, dark: 0x2A261F)
    static let hairlineStrong = Color.dynamic(light: 0xBDB2A0, dark: 0x4A4339)
    static let accent       = Color.dynamic(light: 0xB03D25, dark: 0xE0603F)
    static let accentBright = Color.dynamic(light: 0xC8452B, dark: 0xF07A56)
    static let accentSoft   = Color.dynamic(light: 0xF5E3DC, dark: 0x3A2018)
    static let success      = Color.dynamic(light: 0x3E6B4F, dark: 0x7FB08C)
    static let warning      = Color.dynamic(light: 0x8F5A16, dark: 0xD8A056)
    static let danger       = Color.dynamic(light: 0xA33222, dark: 0xE07A66)

    // Radius
    static let radiusS: CGFloat = 2
    static let radiusM: CGFloat = 4
    static let radiusPill: CGFloat = 999

    // Spacing（4pt 栅格）
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 24
    static let s6: CGFloat = 32
    static let s7: CGFloat = 48

    // Layout
    static let sidebarW: CGFloat = 282
    static let inspectorW: CGFloat = 300
    static let mastheadH: CGFloat = 74
    static let statusH: CGFloat = 38
    static let specRowH: CGFloat = 30
    static let primaryH: CGFloat = 42
}

enum TFont {
    static func songtiBold(_ size: CGFloat) -> Font { .custom("STSongti-SC-Bold", size: size) }
    static func songti(_ size: CGFloat) -> Font { .custom("STSongti-SC-Regular", size: size) }
    static func songtiLight(_ size: CGFloat) -> Font { .custom("STSongti-SC-Light", size: size) }
    static func pingfang(_ size: CGFloat) -> Font { .custom("PingFangSC-Regular", size: size) }
    static func pingfangMedium(_ size: CGFloat) -> Font { .custom("PingFangSC-Medium", size: size) }
    static func pingfangSemibold(_ size: CGFloat) -> Font { .custom("PingFangSC-Semibold", size: size) }
    static func didot(_ size: CGFloat) -> Font { .custom("Didot", size: size) }
    static func menlo(_ size: CGFloat) -> Font { .custom("Menlo-Regular", size: size) }
    static func menloBold(_ size: CGFloat) -> Font { .custom("Menlo-Bold", size: size) }
    static func caps(_ size: CGFloat) -> Font { .custom("AvenirNext-DemiBold", size: size) }
}

// MARK: - 原子组件

struct Hairline: View {
    var vertical = false
    var color: Color = Tok.hairline
    var body: some View {
        Rectangle().fill(color)
            .frame(width: vertical ? 1 : nil, height: vertical ? nil : 1)
    }
}

/// 拉丁小 caps 微标签（编号/栏目名/状态）
struct MicroLabel: View {
    let text: String
    var color: Color = Tok.inkMuted
    var size: CGFloat = 9.5
    var tracking: CGFloat = 1.7
    init(_ text: String, color: Color = Tok.inkMuted,
         size: CGFloat = 9.5, tracking: CGFloat = 1.7) {
        self.text = text
        self.color = color
        self.size = size
        self.tracking = tracking
    }
    var body: some View {
        Text(text)
            .font(TFont.caps(size))
            .tracking(tracking)
            .foregroundStyle(color)
            .lineLimit(1)
    }
}

/// 中文微标签（编号/栏目名）
struct MicroLabelCN: View {
    let text: String
    var color: Color = Tok.inkMuted
    var size: CGFloat = 10
    init(_ text: String, color: Color = Tok.inkMuted, size: CGFloat = 10) {
        self.text = text
        self.color = color
        self.size = size
    }
    var body: some View {
        Text(text)
            .font(TFont.pingfang(size))
            .tracking(1.2)
            .foregroundStyle(color)
            .lineLimit(1)
    }
}

/// 栏目头：编号 + 中文标题 + 右侧英文小 caps + 发丝线
struct SectionHeader: View {
    let index: String
    let title: String
    var trailing: String? = nil
    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 9) {
                Text(index).font(TFont.didot(13)).foregroundStyle(Tok.accent)
                Text(title)
                    .font(TFont.pingfangMedium(12.5))
                    .tracking(0.4)
                    .foregroundStyle(Tok.ink)
                Spacer(minLength: 4)
                if let trailing {
                    MicroLabel(trailing, color: Tok.inkMuted, size: 9)
                }
            }
            .padding(.bottom, 7)
            Hairline()
        }
    }
}

/// 规格行：左标签右数值
struct SpecRow: View {
    let label: String
    let value: String
    var mono = true
    var valueColor: Color = Tok.ink
    var showLine = true
    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(label)
                    .font(TFont.pingfang(11.5))
                    .tracking(0.3)
                    .foregroundStyle(Tok.inkMuted)
                Spacer(minLength: 4)
                Text(value)
                    .font(mono ? TFont.menlo(11.5) : TFont.pingfangMedium(11.5))
                    .foregroundStyle(valueColor)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(height: Tok.specRowH)
            if showLine { Hairline(color: Tok.hairlineSoft) }
        }
    }
}

struct Swatch: View {
    let hex: String
    var size: CGFloat = 16
    var body: some View {
        Rectangle()
            .fill(Color(hexString: hex))
            .frame(width: size, height: size)
            .overlay(Rectangle().stroke(Tok.ink.opacity(0.18), lineWidth: 0.8))
    }
}

struct StatusDot: View {
    var color: Color = Tok.success
    var size: CGFloat = 6
    var body: some View {
        Circle().fill(color).frame(width: size, height: size)
    }
}

/// 耗材占比条（颜色来自真实色卡）
struct RatioBar: View {
    let fraction: Double
    let color: Color
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle().fill(Tok.hairlineSoft)
                Rectangle().fill(color)
                    .frame(width: max(1, geo.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: 3)
    }
}

// MARK: - 按钮样式

struct InkButtonStyle: ButtonStyle {
    var height: CGFloat = Tok.primaryH
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(TFont.pingfangMedium(12.5))
            .tracking(0.8)
            .foregroundStyle(Tok.paper)
            .frame(maxWidth: .infinity)
            .frame(height: height)
            .background(Tok.ink)
            .clipShape(RoundedRectangle(cornerRadius: Tok.radiusS))
            .opacity(configuration.isPressed ? 0.82 : 1)
    }
}

struct AccentButtonStyle: ButtonStyle {
    var height: CGFloat = Tok.primaryH
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(TFont.pingfangMedium(12.5))
            .tracking(0.8)
            .foregroundStyle(Color.white)
            .padding(.horizontal, 16)
            .frame(height: height)
            .background(Tok.accent)
            .clipShape(RoundedRectangle(cornerRadius: Tok.radiusS))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}

struct GhostButtonStyle: ButtonStyle {
    var height: CGFloat = 26
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(TFont.pingfang(11.5))
            .tracking(0.3)
            .foregroundStyle(Tok.inkSoft)
            .padding(.horizontal, 11)
            .frame(height: height)
            .background(Tok.paper.opacity(configuration.isPressed ? 0.55 : 0.001))
            .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
                .stroke(Tok.hairline, lineWidth: 1))
    }
}

struct PlainHoverStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.55 : 1)
    }
}

// MARK: - 编辑式开关 / 滑杆 / 输入

struct EditorialToggleStyle: ToggleStyle {
    var onColor: Color = Tok.ink
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(spacing: 7) {
                configuration.label
                RoundedRectangle(cornerRadius: Tok.radiusPill)
                    .fill(configuration.isOn ? onColor : Tok.hairlineSoft)
                    .frame(width: 28, height: 16)
                    .overlay(
                        Circle()
                            .fill(configuration.isOn ? Tok.paper : Tok.paperMat)
                            .frame(width: 12, height: 12)
                            .offset(x: configuration.isOn ? 6 : -6)
                    )
                    .overlay(RoundedRectangle(cornerRadius: Tok.radiusPill)
                        .stroke(configuration.isOn ? onColor : Tok.hairline, lineWidth: 1))
            }
        }
        .buttonStyle(.plain)
        .animation(.easeOut(duration: 0.18), value: configuration.isOn)
    }
}

/// 标签 + 滑杆 + 数值（替代系统蓝 tint）
struct EditorialSlider: View {
    let label: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    var step: Double = 0.05
    var format: String = "%.2f"
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline) {
                Text(label).font(TFont.pingfang(11)).foregroundStyle(Tok.inkSoft)
                Spacer()
                Text(String(format: format, value))
                    .font(TFont.menlo(10.5))
                    .foregroundStyle(Tok.ink)
            }
            Slider(value: $value, in: range, step: step)
                .tint(Tok.ink)
                .controlSize(.small)
        }
    }
}

/// 编辑式输入框：下划线式，聚焦时 accent
struct EditorialField: View {
    let placeholder: String
    @Binding var text: String
    var width: CGFloat? = nil
    var mono = true
    @FocusState private var focused: Bool
    var body: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.plain)
            .font(mono ? TFont.menlo(11.5) : TFont.pingfang(12))
            .foregroundStyle(Tok.ink)
            .padding(.horizontal, 8)
            .frame(height: 28)
            .frame(width: width)
            .background(Tok.paperMat)
            .overlay(Rectangle().stroke(focused ? Tok.accent : Tok.hairline, lineWidth: 1))
            .focused($focused)
    }
}

/// HEX 颜色输入（带色块）
struct HexField: View {
    let label: String
    @Binding var text: String
    var body: some View {
        HStack(spacing: 8) {
            Text(label).font(TFont.pingfang(11)).foregroundStyle(Tok.inkMuted)
                .frame(width: 46, alignment: .leading)
            Swatch(hex: text, size: 18)
            EditorialField(placeholder: "#RRGGBB", text: $text)
        }
    }
}

// MARK: - 版面工具

/// 印刷裁切角线（投放区/图版）
struct CropMarks: View {
    var color: Color = Tok.hairlineStrong
    var len: CGFloat = 12
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            Path { p in
                p.move(to: CGPoint(x: 0, y: len)); p.addLine(to: .zero)
                p.addLine(to: CGPoint(x: len, y: 0))
                p.move(to: CGPoint(x: w - len, y: 0)); p.addLine(to: CGPoint(x: w, y: 0))
                p.addLine(to: CGPoint(x: w, y: len))
                p.move(to: CGPoint(x: w, y: h - len)); p.addLine(to: CGPoint(x: w, y: h))
                p.addLine(to: CGPoint(x: w - len, y: h))
                p.move(to: CGPoint(x: len, y: h)); p.addLine(to: CGPoint(x: 0, y: h))
                p.addLine(to: CGPoint(x: 0, y: h - len))
            }
            .stroke(color, lineWidth: 1)
        }
        .allowsHitTesting(false)
    }
}

/// 编辑式分段控件（图纸 / 成品效果）
struct EditorialSegmented: View {
    @Binding var showSecond: Bool
    let first: String
    let second: String
    var body: some View {
        HStack(spacing: 0) {
            segment(first, active: !showSecond) { showSecond = false }
            segment(second, active: showSecond) { showSecond = true }
        }
        .clipShape(RoundedRectangle(cornerRadius: Tok.radiusS))
        .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
            .stroke(Tok.hairlineStrong, lineWidth: 1))
    }

    private func segment(_ title: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(active ? TFont.pingfangMedium(11) : TFont.pingfang(11))
                .foregroundStyle(active ? Tok.paper : Tok.inkSoft)
                .padding(.horizontal, 13)
                .frame(height: 26)
                .background(active ? Tok.ink : Tok.paperMat)
        }
        .buttonStyle(.plain)
    }
}

/// 圆形编号徽记
struct IndexBadge: View {
    let text: String
    var filled = false
    var body: some View {
        Text(text)
            .font(TFont.menlo(9))
            .foregroundStyle(filled ? Tok.paper : Tok.ink)
            .padding(.horizontal, 5)
            .frame(height: 15)
            .background(filled ? Tok.ink : Tok.paper)
            .overlay(Rectangle().stroke(filled ? Tok.ink : Tok.hairline, lineWidth: 1))
    }
}
