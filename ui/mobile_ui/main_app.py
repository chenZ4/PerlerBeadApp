import os
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFloatingActionButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.bottomnavigation import MDBottomNavigationItem
from kivy.animation import Animation
from kivy.properties import StringProperty, ObjectProperty
from kivy.core.window import Window

# 设置窗口（仅用于开发测试预览，打包 APK 后失效）
Window.size = (360, 640)  # 模拟手机屏幕尺寸

# UI 的 Kivy 语言 (KV) 定义
KV = """
MDBoxLayout:
    orientation: 'vertical'

    # 顶部的 Toolbar
    MDTopAppBar:
        title: "Google Design Concept"
        left_action_items: [["menu", lambda x: app.on_menu_click()]]
        elevation: 4
        md_bg_color: app.theme_cls.primary_color
        specific_text_color: 1, 1, 1, 1

    # 主要内容区域和底部导航
    MDBottomNavigation:
        panel_color: app.theme_cls.bg_normal
        text_color_active: app.theme_cls.primary_color
        text_color_normal: 0.5, 0.5, 0.5, 1

        # 首页
        MDBottomNavigationItem:
            name: 'screen 1'
            text: '首页'
            icon: 'home'

            # 使用列表卡片
            ScrollView:
                do_scroll_y: True
                MDBoxLayout:
                    id: home_card_container
                    orientation: 'vertical'
                    padding: dp(16), dp(8), dp(16), dp(100)  # 底部留出 FAB 的空间
                    spacing: dp(16)
                    size_hint_y: None
                    height: self.minimum_height

        # 发现页
        MDBottomNavigationItem:
            name: 'screen 2'
            text: '发现'
            icon: 'magnify'

            MDScreen:
                MDLabel:
                    text: '发现新内容'
                    halign: 'center'
                    font_style: 'H5'
                    theme_text_color: "Secondary"

        # 设置页
        MDBottomNavigationItem:
            name: 'screen 3'
            text: '设置'
            icon: 'cog'

            MDScreen:
                MDLabel:
                    text: '应用程序设置'
                    halign: 'center'
                    font_style: 'H5'
                    theme_text_color: "Secondary"

    # 浮动动作按钮 (FAB)
    MDFloatingActionButton:
        id: fab
        icon: "plus"
        elevation: 6
        md_bg_color: app.theme_cls.accent_color
        text_color: 1, 1, 1, 1
        pos_hint: {'center_x': .85, 'center_y': .1}
        on_release: app.on_fab_click()

# 定义卡片组件
<ContentCard>:
    size_hint_y: None
    height: dp(120)
    padding: dp(16)
    spacing: dp(16)
    radius: [dp(16)]
    elevation: 2
    md_bg_color: 1, 1, 1, 1
    on_release: app.on_card_click(self)

    MDIcon:
        icon: root.icon
        size_hint_x: None
        width: self.texture_size[0]
        pos_hint: {"center_y": .5}
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_dark

    MDBoxLayout:
        orientation: "vertical"
        pos_hint: {"center_y": .5}

        MDLabel:
            text: root.title
            font_style: "Subtitle1"
            bold: True
            theme_text_color: "Primary"

        MDLabel:
            text: root.subtitle
            font_style: "Body2"
            theme_text_color: "Secondary"
"""


# 定义卡片逻辑类
class ContentCard(MDCard):
    title = StringProperty("标题")
    subtitle = StringProperty("副标题描述文字")
    icon = StringProperty("android")


class GoogleDesignApp(MDApp):
    def build(self):
        # 设置 Material Design 主题
        self.theme_cls.primary_palette = "Indigo"  # Google 风格的蓝色
        self.theme_cls.accent_palette = "Pink"  # 强调色
        self.theme_cls.primary_hue = "600"
        self.theme_cls.material_style = "M3"  # 使用 Material Design 3 最新风格

        # 加载 KV 定义
        self.screen = Builder.load_string(KV)
        return self.screen

    def on_start(self):
        # 初始化添加一些卡片内容
        card_data = [
            ("动态消息 1", "这里是描述动态消息内容的简短文字。", "bell-outline"),
            ("新的发现", "在发现页面查看更多新奇内容。", "magnify"),
            ("设置中心", "个性化您的应用程序体验。", "cog-outline"),
            ("项目 4", "更多内容描述...", "package-variant-closed"),
            ("项目 5", "更多内容描述...", "package-variant"),
        ]

        container = self.root.ids.home_card_container
        for title, subtitle, icon in card_data:
            card = ContentCard(title=title, subtitle=subtitle, icon=icon)
            container.add_widget(card)

    def on_menu_click(self):
        print("Menu clicked")
        # 这里可以添加打开侧边栏的逻辑

    def on_fab_click(self):
        print("FAB clicked")
        # 添加丝滑的缩放动画
        fab = self.root.ids.fab
        anim = Animation(scale_x=0.5, scale_y=0.5, duration=0.1) + \
               Animation(scale_x=1, scale_y=1, duration=0.1)
        anim.start(fab)

    def on_card_click(self, card):
        print(f"Card clicked: {card.title}")
        # 添加丝滑的卡片高亮和轻微缩放动画
        # 模仿 Material Design 的点击反馈

        anim = Animation(elevation=12, scale_x=1.02, scale_y=1.02, duration=0.15) + \
               Animation(elevation=2, scale_x=1, scale_y=1, duration=0.15)
        anim.start(card)

        # 将卡片背景色暂时更改
        original_color = card.md_bg_color[:]
        card.md_bg_color = [0.9, 0.9, 0.9, 1]
        # 使用 KivyMD 的动画来还原背景色
        anim_color = Animation(md_bg_color=original_color, duration=0.3, t="in_out_quad")
        anim_color.start(card)


if __name__ == "__main__":
    GoogleDesignApp().run()