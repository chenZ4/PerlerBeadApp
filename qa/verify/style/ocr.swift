import AppKit
import Vision

// T17：独立 OCR 工具（macOS Vision，无第三方依赖）
// 用法: ocr <image files...> → JSON: [{file,width,height,texts:[{text,conf,x,y,w,h}]}]
// bbox 归一化（0..1），原点已转换为左上。
let args = Array(CommandLine.arguments.dropFirst())
var results: [[String: Any]] = []
for path in args {
    guard let img = NSImage(contentsOfFile: path),
          let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let cg = rep.cgImage else {
        results.append(["file": path, "error": "load failed"])
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    if #available(macOS 13.0, *) { req.revision = VNRecognizeTextRequestRevision3 }
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    } catch {
        results.append(["file": path, "error": "ocr failed: \(error)"])
        continue
    }
    var texts: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let cand = o.topCandidates(1).first else { continue }
        let bb = o.boundingBox
        texts.append([
            "text": cand.string,
            "conf": Double(cand.confidence),
            "x": Double(bb.minX),
            "y": Double(1.0 - bb.maxY),
            "w": Double(bb.width),
            "h": Double(bb.height),
        ])
    }
    results.append(["file": path, "width": rep.pixelsWide, "height": rep.pixelsHigh, "texts": texts])
}
let data = try JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([0x0A]))
