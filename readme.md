# The Disinfectant Project

<p align="center">
  <img src="images/cover.png" alt="The Disinfectant Project Cover" width="800">
</p>

消毒水行动是一个开发中的数据采集项目，旨在为"消毒水行动"网页应用提供淘宝商品数据源。该项目目前处于 demo 阶段，利用 Python 爬虫技术从淘宝网获取商品信息。

## 项目状态

✅ **可用版本**
- 当前版本：v0.2.0
- 两个主要功能模块已完成并可用：
  - 单个商品详情爬取 ([`single_product_scraper.py`](src/single_product_scraper.py))
  - 批量店铺商品爬取 ([`taobao_scraper.py`](src/taobao_scraper.py))

## 已实现功能

### ✅ 单个商品详情爬取 ([`single_product_scraper.py`](src/single_product_scraper.py))
- **功能**：爬取单个淘宝商品的完整信息，包括：
  - 商品标题和店铺信息
  - 所有颜色/款式变体及其图片
  - 每个款式对应的尺码及库存情况
  - 用户评价（前5条）
  - 商品参数详情
  - 图文详情中的所有图片
  - 价格信息和优惠券信息
- **输出格式**：JSON + 可读文本 + 原始 HTML 保存
- **特点**：结构化数据返回，支持传入现有 WebDriver 实例

### ✅ 批量店铺商品爬取 ([`taobao_scraper.py`](src/taobao_scraper.py)) - **已可用**
- **功能**：批量爬取指定店铺中的所有商品信息，包括：
  - 自动获取店铺内所有商品链接
  - 爬取每个商品的完整详细信息
  - 生成索引 CSV 文件和任务汇总报告
  - 详细的运行日志记录
- **输出结构**：
  ```
  scraped_data/shop_scrape_[时间戳]/
  ├── scraping.log              # 爬取日志
  ├── index.csv                 # 商品索引汇总
  ├── task_summary.txt          # 任务报告
  ├── shop_[店铺名].txt          # 各店铺汇总
  └── products/                 # 商品详情目录
      └── [商品ID]/
          ├── product_data.json
          ├── product_data_readable.txt
          ├── parameters_raw.html
          └── image_details_raw.html
  ```
- **特点**：支持多店铺配置，完整保留所有原始数据

## 开发中功能

### 🚧 商品详情页辅助爬取 ([`detail_scraper.py`](src/detail_scraper.py))
- **状态**：辅助模块，功能有限
- **用途**：为批量爬取提供商品详情页数据提取支持

### 🚧 款式信息解析 ([`style_scraper.py`](src/style_scraper.py))
- **状态**：实验性功能
- **用途**：解析商品的款式和尺码信息

## 安装与配置

### 环境要求
- Python 3.14.2+
- Chrome 浏览器
- ChromeDriver（自动管理）

### 安装步骤

1. 克隆项目：
```bash
git clone https://github.com/AndreaFrederica/TheDisinfectantProject.git
cd TheDisinfectantProject
```

2. 使用 pixi 安装依赖（推荐）：
```bash
pixi install
```

或使用 pip 手动安装：
```bash
pip install selenium webdriver-manager pyjson5 json5 beautifulsoup4 html5lib
```

3. 配置店铺信息（仅批量爬取需要）：

编辑 [`src/shops.json5`](src/shops.json5) 文件，添加要爬取的店铺：

```json5
[
  {
    "name": "店铺名称",
    "url": "https://shop107534922.taobao.com/search.htm"
  },
  {
    "name": "另一个店铺",
    "url": "https://shop123456789.taobao.com/search.htm"
  }
]
```

## 快速开始

### 1. 爬取单个商品

```bash
# 使用默认URL
python src/single_product_scraper.py

# 指定商品URL
python src/single_product_scraper.py "https://item.taobao.com/item.htm?id=123456789"
```

输出文件将保存在 `scraped_data/scraped_data_[时间戳]/` 目录下：
- `product_data.json` - 完整的JSON数据（适合程序处理）
- `product_data_readable.txt` - 格式化的可读文本（方便查看）
- `parameters_raw.html` - 原始参数HTML（调试用）
- `image_details_raw.html` - 原始图文详情HTML（调试用）

### 2. 批量爬取店铺商品（新功能）

```bash
# 直接运行（使用 shops.json5 配置）
python src/taobao_scraper.py
```

输出文件将保存在 `scraped_data/shop_scrape_[时间戳]/` 目录下：
- `scraping.log` - 详细的爬取日志
- `index.csv` - 所有商品的索引汇总
- `task_summary.txt` - 任务完成报告
- `shop_[店铺名].txt` - 各店铺的商品列表
- `products/` - 每个商品的详细文件夹

### 3. 在其他程序中使用

```python
from src.single_product_scraper import scrape_product_data
from src.taobao_scraper import scrape_shops

# 爬取单个商品
product_data = scrape_product_data("https://item.taobao.com/item.htm?id=123456789")

# 批量爬取店铺
shops = [{"name": "店铺名", "url": "店铺URL"}]
products = scrape_shops(shops, output_dir="my_output")
```

## 输出数据格式

### 主要输出：单个商品数据结构

```json
{
  "product_info": {
    "title": "商品标题",
    "url": "商品URL",
    "shop": {
      "name": "店铺名称",
      "url": "店铺链接",
      "rating": "店铺评分",
      "good_review_rate": "好评率"
    }
  },
  "styles": [
    {
      "style_name": "颜色/款式名称",
      "image_url": "款式图片URL",
      "available": true,
      "sizes": [
        {
          "name": "尺码名称",
          "available": true
        }
      ]
    }
  ],
  "product_details": {
    "reviews": [
      {
        "user": "用户名",
        "meta": "购买信息",
        "content": "评价内容",
        "images": ["评价图片URL"]
      }
    ],
    "parameters": {
      "参数名": "参数值"
    },
    "image_details": ["图文详情图片URL"]
  }
}
```

### 计划中的批量爬取输出（开发中）

- **格式**：CSV
- **字段**：商品名称、价格、库存、主图、商品链接
- **状态**：功能开发中

## 技术实现

### 核心技术栈
- **Selenium WebDriver** - 模拟浏览器操作，应对动态加载
- **Chrome Profile** - 保持登录状态，避免频繁登录
- **多重选择器策略** - 应对淘宝页面结构变化
- **JSON5** - 灵活的配置文件格式

### 当前实现特点
1. **反爬虫策略**：
   - 禁用自动化控制特征 (`--disable-blink-features=AutomationControlled`)
   - 使用真实的 Chrome 用户数据目录
   - 模拟真实的点击和滚动操作

2. **数据提取**：
   - 多种 CSS 选择器备选方案
   - 保存原始 HTML 便于调试
   - JSON + 文本双重输出格式

3. **错误处理**：
   - 完善的异常捕获机制
   - 调试文件自动保存
   - 详细的日志输出

## 使用须知

⚠️ **重要提示**
- 本项目仅用于学习和研究目的
- 请遵守淘宝网的使用条款和 robots.txt 协议
- 请合理控制爬取频率，避免给服务器造成压力
- 不得用于商业用途或大规模数据采集

### 运行要求
1. **登录要求**：
   - 需要登录淘宝账号才能访问部分商品信息
   - 程序会预留 5-30 秒手动登录时间
   - 登录状态会保存在 `chrome_profile` 目录

2. **网络环境**：
   - 建议使用稳定的网络环境
   - 如遇网络超时，可适当调整代码中的延迟时间
   - 部分地区可能需要配置代理

3. **常见问题**：
   - 如果页面加载失败，尝试增加 `time.sleep()` 的延迟时间
   - Chrome 浏览器需要保持最新版本
   - 确保 ChromeDriver 版本与 Chrome 浏览器版本匹配

## 开发信息

- **IDE**: VS Code
- **包管理**: pixi
- **Python版本**: 3.14.2+
- **项目状态**: Demo 开发中

## 项目定位

本项目是"消毒水行动"网页应用的数据采集组件，主要职责是：
- 从淘宝网采集商品信息
- 结构化存储商品数据
- 为前端应用提供数据支持

## 未来计划

- [ ] 增加更多电商平台支持（天猫、京东等）
- [ ] 优化数据采集效率和并发处理
- [ ] 添加数据清洗和验证功能
- [ ] 实现 RESTful API 接口供前端调用
- [ ] 增加分布式爬取支持
- [ ] 添加增量更新功能，避免重复爬取
- [ ] 实现数据可视化和统计分析模块

## 贡献

当前处于开发阶段，欢迎提交 Issue 反馈问题。功能开发请先创建 Issue 讨论。

## 许可证

本项目采用 Mozilla Public License 2.0 (MPL-2.0) 许可证。

### MPL 2.0 许可证要点

- **商业使用**：允许商业使用
- **修改**：允许修改和分发
- **专利授权**：提供专利授权
- **责任限制**：软件按"原样"提供，不提供任何明示或暗示的担保
- **商标使用**：不授予商标使用权

### 使用要求

- **保留声明**：必须在分发时保留原始版权声明和许可证声明
- **披露源码**：如果对修改后的文件进行分发，需要提供修改部分的源代码
- **相同许可证**：修改后的文件必须继续使用 MPL 2.0 许可证

### 项目特别说明

虽然本项目使用 MPL 2.0 许可证，但请确保：
1. 遵守淘宝网的使用条款和 robots.txt 协议
2. 合理控制爬取频率，避免给服务器造成压力
3. 不得将本项目用于违反法律法规或侵犯他人权益的行为

完整许可证文本请查看项目根目录下的 [LICENSE](LICENSE) 文件。