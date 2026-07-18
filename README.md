# Atlas Web Alpha 0.2 — GitHub Pages 部署版

这是可直接上传到 GitHub 仓库根目录的静态网站版本。

## 必须上传的内容

- `index.html`
- `styles.css`
- `app.js`
- `manifest.webmanifest`
- `sw.js`
- `icon-180.png`、`icon-192.png`、`icon-512.png`
- `assets` 文件夹
- `data` 文件夹

## 发布方式

仓库上传完成后，在 GitHub 打开：

`Settings → Pages → Build and deployment → Source: Deploy from a branch`

然后选择：

- Branch：`main`
- Folder：`/(root)`

保存后等待 GitHub Pages 发布。
