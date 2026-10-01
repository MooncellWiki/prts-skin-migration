# 新旧皮肤切换按钮（`skin-switch`）

2026-10-01 · `微件:SkinSwitch`（源文件 `微件_SkinSwitch.wiki`）· 脚本 `scripts/skin_switch_apply.py`

状态：**已上线**（2026-10-01 18:03）。微件、后端钩子、Varnish 三处都在线上，匿名 cookie 换肤经 CDN 实测可用。
还没做的：docker-config 已提交推送（47cca4f），但**还没在 Portainer 部署**，线上靠热加载的 `skincookie_20261001` 撑着，容器重启会丢；还没有页面用这个微件。

## 1. 用法

```wikitext
{{#widget:SkinSwitch}}
```

| 当前皮肤 | 按钮 | 点击 |
| --- | --- | --- |
| 不是 Arknights | 「切换到新版皮肤」（实底） | 切到 Arknights，提示「正在切换到新版皮肤…」 |
| Arknights | 「恢复默认皮肤」（描边） | 回到 `old` 指定的皮肤，默认是站点默认皮肤 |

解析缓存各皮肤共用，所以两种文字都输出，由 `body.skin-arknights` 的 CSS 二选一，不闪。一页放多个时样式和脚本只输出一次。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `old` | 空 | 从新皮肤点回去的目标。空 = 站点默认（清掉偏好 / cookie）。**默认皮肤换成 Arknights 之后要填 `vector`**，否则点了没变化 |
| `anon` | `cookie` | 未登录访客怎么切，见 §2。填 `useskin` 则只对当前页面生效 |
| `cookie` | `akskin` | cookie 名，要和后端钩子、VCL 一致 |
| `new_text` / `old_text` | 见上 | 按钮文字 |

## 2. 各种人点了之后发生什么

| 谁 | 做法 | 能保持吗 |
| --- | --- | --- |
| 登录用户 | `action=options` 写 `skin` 偏好（回默认时是重置），然后刷新 | 能，跨设备 |
| 登录用户，在 m.prts.wiki | 同上，再跳到 `prts.wiki/…?mobileaction=toggle_view_desktop`（Varnish 现成的开关，种 `stopMobileRedirect`）。移动版强制 Minerva，新皮肤只在主域上有。同时记一个 `akskin_m` cookie，点回旧皮肤时走 `toggle_view_mobile` 把人送回 m. | 能 |
| 未登录（默认 `anon=cookie`） | 写 `akskin=arknights`（`Domain=.prts.wiki`，1 年），刷新 | 能，单浏览器。Safari 对 JS 写的 cookie 最多留 7 天 |
| 未登录，`anon=useskin` | 给当前 URL 加 `?useskin=arknights`，并提示「未登录时只对当前页面生效」 | **不能**，换页就没了 |

登录用户也会顺手写 `akskin` cookie：Varnish 靠它不把手机 UA 引去 m.。

## 3. 未登录换肤方案

`微件:LangSwitcher` 的匿名语言 cookie（`ak_aklanguage`）就是现成的先例，皮肤照这个路子走，三层都要认这个 cookie：

| 层 | 现状 | 要做的 | 状态 |
| --- | --- | --- | --- |
| 阿里云 CDN | 响应带 `Vary: Cookie`，实测带不同 cookie 的请求各自回源（同 URL 第二次 HIT，加一个 cookie 后 MISS） | 不用改 | ✔ |
| Varnish | 匿名请求只留 `ak_aklanguage`，其余 cookie 全部剥掉；归一化后的 cookie 进 `vcl_hash` | `varnish.patch`：认 `akskin=(arknights\|vector)`，留给后端并进缓存键；带这个 cookie 的不再按 UA 302 去 m.，在 m. 上的 302 回主域 | **已热加载**为 `skincookie_20261001`（18:02，`boot` 留作回滚）；docker-config 47cca4f 已推送，待 Portainer 部署 |
| MediaWiki | 匿名用户只有 `$wgDefaultSkin` | `etc/post-config.php` 加 `RequestContextCreateSkin` 钩子：未登录 + cookie 值是已安装皮肤 + 没有 `useskin` → 用它 | **已在线上**（17:57，备份 `post-config.php.bak-20261001-skincookie`） |

只上了钩子、Varnish 还没改时（17:59），cookie 到不了后端，现网行为不变：

| 请求 | 直连后端 | 经 Varnish |
| --- | --- | --- |
| 无 cookie | Vector | Vector |
| `akskin=arknights` | **Arknights** | Vector（cookie 被剥） |
| `akskin=nope` | Vector | — |
| `akskin=arknights` + `?useskin=vector-2022` | Vector 2022 | — |

近 3 分钟 PHP 0 fatal、Caddy 0 个 5xx。

没选的方案：

- **纯前端（localStorage 记住，每页加载后自己跳 `?useskin=`）**：不用动服务器，但每次进站都要先出旧皮肤再跳一次，
  还得往全站 JS 里挂一段，分享出去的链接也带着 `useskin`。`anon=useskin` 只取了它「当前页面预览」那一半。
- **cookie 直接改 `$wgDefaultSkin`**：登录但没选过皮肤的人也会被 cookie 带着走，和偏好设置里显示的默认值对不上。

### 上线后验证（18:03，经 Varnish）

| 请求 | 结果 |
| --- | --- |
| 桌面 UA，无 cookie | Vector，HIT（原来的缓存对象，没有 ban） |
| `akskin=arknights` | Arknights，第一次 MISS、第二次 HIT |
| `foo=1; akskin=arknights; _ga=…` | Arknights，HIT 同一个对象（cookie 归一化了） |
| `akskin=timeless` / `xakskin=arknights` | Vector，HIT 默认对象（不在白名单） |
| `ak_aklanguage=en; akskin=arknights` | Arknights，单独的缓存键 |
| 手机 UA，无 cookie | 302 → m.prts.wiki（不变） |
| 手机 UA，`akskin=arknights` | 200 Arknights，不再跳 m. |
| m.prts.wiki，无 cookie | Minerva（不变） |
| m.prts.wiki，`akskin=arknights` | 302 → prts.wiki |

近 3 分钟 PHP 0 fatal、Caddy 0 个 5xx。

外网经 CDN、未登录的浏览器（按钮是把 `action=parse` 的输出注入到 `阿` 页面里点的，线上还没有页面用它）：
点「切换到新版皮肤」→ 刷新后 Arknights，另一个页面（`银灰`）也是 Arknights；点「恢复默认皮肤」→ cookie 清掉，回到 Vector。

每个选了新皮肤的匿名访客走的是另一套缓存键，这部分页面要重新回源渲染（Arknights 约 0.5 s/页，解析缓存共用）。

回滚：`post-config.php` 删掉末尾那段钩子（或从备份恢复）；VCL `vcl.use` 回上一份。

## 4. 沙箱验证

`http://localhost:8080/w/User:Akdev/SkinSwitch`（沙箱默认皮肤是 Arknights，所以用 `old=vector` 来回切）：

- 未登录 `anon=cookie`：Arknights → Vector → Arknights，cookie 跟着变，URL 不变
- 未登录 `anon=useskin`：URL 在 `?useskin=vector` / `?useskin=arknights` 之间换
- 登录：偏好 `skin` 写成 `vector` 再写回；登录状态下把 cookie 改成别的皮肤，页面不受影响
- 参数里的 HTML 被转义；一页三个按钮只输出一份 `<style>` / `<script>`
- 截图：`build/shots/skin-switch-vector.png` / `skin-switch-arknights.png`

没验证的：在 m.prts.wiki 上点按钮的整条路径（只验了 Varnish 的跳转），以及 Minerva 下按钮的样子。
