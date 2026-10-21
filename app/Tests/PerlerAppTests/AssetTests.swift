import XCTest
@testable import PerlerApp

final class AssetTests: XCTestCase {
    func testCoverHeroAssetLoads() {
        let hero = EditorialAssets.heroPhotoToBeadsCover
        XCTAssertNotNil(hero, "hero_photo_to_beads_cover 未加载到（封面大图）")
        if let hero {
            XCTAssertGreaterThan(hero.size.width, 2000)
            XCTAssertEqual(hero.size.width / hero.size.height, 2400.0 / 1800.0, accuracy: 0.02)
        }
    }
}
