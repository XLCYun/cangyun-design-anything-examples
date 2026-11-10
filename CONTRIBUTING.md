# 贡献风格示例

## 表单投稿

在[投稿表单](https://github.com/XLCYun/cangyun-design-anything-examples/issues/new?template=style-example.yml)按顺序上传一至十张预览图。填写页面用途、值得借用的视觉特征、作者和示例许可。有参考素材时，每行填写一个来源链接及相应署名和许可。可附提示词或已有的 `example.json`。

表单和附件公开可见。上传前请检查图片、提示词和源文件是否适合公开，并确认有权按所填许可分享。

工作流处理标题以 `[风格投稿]` 开头的 Issue。材料通过校验后，机器人把图片和元数据放到示例目录，在 `submissions/issue-编号` 分支上开草稿 PR。维护者在 PR 中决定是否收录，合并后会关闭关联的 Issue。

每条 Issue 对应一份草稿 PR。生成前可以编辑 Issue 补充材料，校验结果在[工作流运行记录](https://github.com/XLCYun/cangyun-design-anything-examples/actions/workflows/style-submission.yml)中查看。PR 创建后，请在对应 PR 中讨论修改。

自动生成的示例目录带有 Issue 编号。已知风格可填它的英文目录名。工作流会为其他风格生成稳定目录名，并把展示名称记录在 `example.json` 的 `style` 字段中。

## 命令行投稿

用 GitHub CLI 把 `submission.md` 提交为 Issue。

```bash
gh issue create --repo XLCYun/cangyun-design-anything-examples \
  --title "[风格投稿] 大学介绍页" --body-file submission.md
```

在正文用以下三级标题填写材料。预览链接按展示顺序列出。支持 GitHub Issue 图片附件和可公开读取的 `raw.githubusercontent.com` 文件链接。

```markdown
### 类别

ppt

### 风格名称

俄国构成主义

### 风格目录名

russian-constructivism

### 预览图片

![封面](https://raw.githubusercontent.com/your-name/your-repo/main/01-cover.webp)
![内容页](https://raw.githubusercontent.com/your-name/your-repo/main/02-content.webp)

### 示例元数据

[example.json](https://raw.githubusercontent.com/your-name/your-repo/main/example.json)

### 公开确认

- [x] 我确认这些材料可以公开，并授权按元数据填写的许可收入示例仓库。
```

「示例元数据」也接受直接粘贴的 JSON。文件格式见下方示例，`images` 须与预览图的数量、顺序和实际格式一致。使用表单字段时，可以用「示例名称」「示例说明」「作者」「示例许可」代替「示例元数据」。每张预览图最长边为 4096 像素以内，单张最多 10 MiB，合计最多 32 MiB。可编辑源文件通过人工 PR 提交。

## 直接提 PR

Fork 本仓库，为每条示例新建 `examples/<ppt|ui|paper>/<style-slug>/<example-slug>/`。风格和示例目录名使用小写英文字母、数字和连字符。

在示例目录保存 `example.json` 和 `images/`。图片使用 WebP、PNG 或 JPEG，按想展示的顺序列在 `images` 字段中，第一张作为封面。每张图配一句说明。编辑源文件可放在 `source/` 并列入 `sourceFiles`。

下方是 `examples/ppt/russian-constructivism/fudan-intro/example.json` 的填写示意。[JSON Schema](schemas/example.schema.json)

```json
{
  "$schema": "../../../../schemas/example.schema.json",
  "title": "俄国构成主义风格的大学介绍",
  "description": "适合简短介绍和章节开场。用红色楔形把视线引向创校年份，粗黑标题与白圆形成对比。",
  "author": "your-github-name",
  "license": "CC-BY-4.0",
  "images": [
    {
      "file": "images/01-cover.webp",
      "caption": "封面使用斜向楔形和白圆突出年份。"
    },
    {
      "file": "images/02-content.webp",
      "caption": "内容页用同一组红黑白配色组织两块信息。"
    }
  ]
}
```

`license` 写明本示例的公开许可，可用 SPDX 标识。有参考作品时用 `references` 记录链接、署名及许可。提交前确认元数据里的图片和源文件路径都能在示例目录内找到。

## 维护工作流

在仓库的 Settings → Actions → General → Workflow permissions 开启 **Allow GitHub Actions to create and approve pull requests**。工作流的任务权限已声明为 `contents: write` 和 `pull-requests: write`。[GitHub 设置说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests)
