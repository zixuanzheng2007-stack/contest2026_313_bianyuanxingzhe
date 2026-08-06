# Windows 本地拉起说明（边缘行者）

专属仓：https://github.com/open-vela/contest2026_313_bianyuanxingzhe  
分支：`dev-ai-contest-2026`

## 当前本机状态

- 已 clone 专属仓到：`e:\openvela\contest2026_313_bianyuanxingzhe`
- 已并入本地材料：
  - `docs/` — 技术方案 / 换板 / 接线等
  - `edge-walker/` — 无板主机工程（假雷达→策略→Agent）
- 远程：`upstream` → `open-vela/contest2026_313_bianyuanxingzhe`（组委会仓）

## 立刻可做（Windows）

```powershell
cd e:\openvela\contest2026_313_bianyuanxingzhe\edge-walker
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts\run_demo.py
```

请在 Cursor 中 **打开此专属仓目录** 作为工作区根目录。

## 推送前：先 Fork

组委会仓有分支保护，需：

1. 浏览器打开专属仓 → **Fork** 到你的 GitHub 账号  
2. 本机添加你的 fork 为 `origin`：

```powershell
cd e:\openvela\contest2026_313_bianyuanxingzhe
git remote add origin https://github.com/<你的用户名>/contest2026_313_bianyuanxingzhe.git
git checkout -b feature/host-edge-walker
git add docs edge-walker .gitignore
git commit -m "Add host-side edge-walker and team docs for board-less development."
git push -u origin HEAD
```

3. 向 **组委会专属仓**（或你的流程要求的目标）开 PR 并自行合入（以官方《参赛代码提交指南》为准）。

## openvela 全量工程（需 Ubuntu）

完整编译/模拟器不在 Windows 上做，在 VMware Ubuntu 22.04：

```bash
mkdir -p ~/openvela && cd ~/openvela
repo init -u https://github.com/open-vela/contest2026_313_bianyuanxingzhe \
  -b dev-ai-contest-2026 -m contest2026_313_bianyuanxingzhe.xml
repo sync -c -j8
```

同步后专属仓在 `~/openvela/contest2026_313_bianyuanxingzhe/`，可把本机已改的 `docs/`、`edge-walker/` 再拷进去或用 git 拉你的 fork。
