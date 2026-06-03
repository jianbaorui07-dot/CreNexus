# Blender 绘制学习区

这个区域记录一次本地 Blender 素材库的学习结果。目标不是发布原始素材，而是从别人已经做好的模型、灯光、材质和练习文件里拆出可复用的方法：如何用 Blender 建模、上材质、打光、取景并渲染成图。

## 数据边界

- 原始素材位于本地磁盘，未提交到 GitHub。
- 仓库只保留脱敏后的索引、统计和学习笔记。
- 数据文件不包含本机绝对路径，不包含 `.blend`、贴图、HDR、压缩包等原始资产。
- 公开内容用于学习“绘制方法”和“项目组织方式”，不是素材再分发。

## 已学习的数据规模

- 文件总数：778
- 文件夹总数：78
- 总体量：约 50.65 GB
- 可直接作为 Blender 学习案例的模型文件：34 个
- 材质贴图相关文件：132 个
- HDR/EXR 灯光环境文件：108 个
- 压缩素材包：500 个

## Blender 场景剖析结果

已用 Blender 5.1 后台打开并分析 25 个 `.blend` 文件，全部成功，失败数为 0。分析过程自动禁用了素材文件内嵌脚本，没有运行未知脚本。

抽取到的关键结构：

| 指标 | 数量 |
| --- | ---: |
| 场景 profile | 25 |
| 总对象数 | 1779 |
| Mesh 对象 | 1583 |
| 材质 | 360 |
| 灯光 | 35 |
| 相机 | 31 |
| Armature 骨骼对象 | 11 |

渲染引擎分布：

| 引擎 | 场景数 | 学习意义 |
| --- | ---: | --- |
| BLENDER_EEVEE | 21 | 更偏实时预览、角色展示、快速出图和风格化绘制 |
| CYCLES | 4 | 更适合产品、金属、车体、真实光照和高质量材质观察 |

高频修改器：

| 修改器 | 次数 | 可学习点 |
| --- | ---: | --- |
| SUBSURF | 770 | 用低模控制大形，再用细分获得柔和轮廓 |
| NODES | 426 | 程序化几何或材质节点是复杂资产的重要来源 |
| SOLIDIFY | 244 | 衣服、薄片、装甲边缘常用厚度控制 |
| MIRROR | 229 | 对称建模是角色、车辆、机械件的核心流程 |
| ARMATURE | 136 | 角色绘制离不开绑定、姿势和骨骼结构 |
| BEVEL | 59 | 产品、机械和车辆依赖倒角吃高光 |

## 这个素材库教会我的核心方法

1. 先学轮廓，不急着堆细节。角色、车辆、道具都大量依赖 `Mirror` 和 `Subsurf`，说明作者先控制大形和对称关系，再逐步提高细节。
2. 材质不是单纯贴图。可学习重点是材质节点如何组织 base color、roughness、normal、emission、透明和金属感。
3. 灯光决定“画面像不像作品”。HDR/EXR 环境库和单独的“蓝紫打光”案例说明，绘制图像时要先定光照气氛，再调材质。
4. 相机是构图工具。31 个相机说明很多文件不是纯模型仓库，而是可研究镜头、焦段、展示角度和成图构图的场景。
5. 角色学习要拆成四层：身体比例、衣物厚度、头发/装饰、骨骼姿势。不要把角色当一个整体硬啃。
6. 车辆和硬表面学习要看倒角、镜像、细分、节点组织，尤其是边缘高光和材质反射。
7. 练习素材适合反向临摹：先隐藏材质看白模，再恢复材质看贴图，最后恢复灯光和相机看最终画面。

## 文件说明

- `LEARNING_NOTES.md`：面向创作学习的中文总结。
- `PRACTICE_ROADMAP.md`：按阶段练习 Blender 绘制图的路线。
- `experiments/`：逐个打开案例后的实验记录。
- `data/asset_summary_redacted.json`：素材库脱敏统计。
- `data/asset_inventory_redacted.csv`：逐文件脱敏索引。
- `data/blend_scene_profiles_redacted.json`：`.blend` 场景结构 profile。
- `scripts/analyze_blender_learning_assets.py`：生成脱敏资产索引。
- `scripts/blender_scene_profile.py`：用 Blender 后台生成场景剖析。

## 复现命令

```powershell
$env:BLENDER_ASSET_ROOT="<local Blender asset folder>"
$env:BLENDER_EXE="<path to blender.exe>"

python scripts\analyze_blender_learning_assets.py --root $env:BLENDER_ASSET_ROOT --out-dir docs\blender-drawing-learning\data

& $env:BLENDER_EXE --background --python scripts\blender_scene_profile.py -- --root $env:BLENDER_ASSET_ROOT --out docs\blender-drawing-learning\data\blend_scene_profiles_redacted.json
```
