import XCTest
@testable import PerlerApp

final class AssetTests: XCTestCase {
    func testHeroAssetLoads() {
        // SPM 资源包 / 源码树回退至少有一条可用；缺失时开始页会退化为纯排版占位
        let hero = EditorialAssets.heroPhotoToBeads
        XCTAssertNotNil(hero, "hero_photo_to_beads 未加载到（检查 Resources 与 Package.swift resources）")
        if let hero {
            XCTAssertGreaterThan(hero.size.width, 1000)
            XCTAssertEqual(hero.size.width / hero.size.height, 2400.0 / 1333.0, accuracy: 0.02)
        }
    }
}
