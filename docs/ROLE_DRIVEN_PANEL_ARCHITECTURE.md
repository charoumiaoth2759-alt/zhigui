# Role-Driven Panel Architecture（板件角色驱动架构）

系统已进入 **配置驱动管线** 阶段（见 [`docs/PANEL_ADD_PIPELINE.md`](PANEL_ADD_PIPELINE.md)）：

```
Face → Space → Panel → Command → Solver → Topology → Occupancy → FaceRegistry → View3D
```

新增板件：**仅** `PanelRole` + `PanelRoleSpec` 注册表 + `panel_face_mapper` + `panel_pipeline`；**禁止**复制 `left_panel` 代码。

---

## 三件套

| 组件 | 模块 |
|------|------|
| **Mapper** | `core/panel/panel_face_mapper.py` — `PanelRole` ↔ `FaceType` |
| **Factory / 注册表** | `core/panel/panel_role_spec.py` — `PanelRoleSpec` |
| **管线** | `core/panel/panel_pipeline.py` — `create_add_panel_command` |

`side_panel_spec.py` 为兼容 re-export；新代码请用 `PanelRoleSpec`。

---

## 统一侧板系统（LEFT / RIGHT 已注册）

| 层 | 职责 | 模块 |
|----|------|------|
| 角色↔面 | `PanelRole` ↔ `FaceType` | `core/panel/panel_face_mapper.py` |
| 规格注册 | `PanelRoleSpec` | `core/panel/panel_role_spec.py` |
| 构造 / 挂载 | `build_side_panel` / `mount_side_panel` | `core/panel/cabinet_space_panel_cmd.py` |
| 求解落位 | `solve_side_panel(panel, space)` | `core/panel/side_panel_solver.py` |
| 命令 | `CommandFactory.create_add_panel_command` → `panel_pipeline` | `commands/command_factory.py` |
| 悬停/点击 | `process_face_hover` / `process_face_click` | `ui/interaction/face_interaction.py` |
| 悬停预览 | `InteractionPreviewSpec` | `ui/interaction/preview_spec.py` |
| 拓扑 | `rebuild_after_solver` | `core/space/space_consistency_manager.py` |
| 面注册表 | `face_registry.rebuild_face_registry` | `core/space/face_registry.py` |
| 主题色 | `PREVIEW_COLOR` / `PANEL_COLOR` / `HOVER_COLOR` | `ui/theme_constants.py` |

**扩展**：在 `panel_role_spec._PANEL_ROLE_SPECS` 增加一条；`panel_commands.register_handlers()` 自动注册命令名。

---

## 后续板件（TOP / BOTTOM / DIVIDER）

与侧板相同管道，仅扩展注册表与 `panel_placement` 分发：

| 计划角色 | 锚定 / 面 | 禁止做法 |
|----------|-----------|----------|
| `TOP` / `BOTTOM` | `FaceType.TOP` / `BOTTOM` | 独立 `add_top_panel_system/` |
| `SHELF` / `DIVIDER` | `AUTO_PLACED` | 独立悬停 / undo 子系统 |

---

## 管线日志

见 `core/cabinet_pipeline_log.py`；阶段标记 `[Pipeline] Face` … `[FACE_REGISTRY] rebuild`。

---

## 反模式（代码评审时拒绝）

- 复制 `add_left_panel` / `submit_add_left_panel` 实现新板件
- `solve_left_panel()` / `solve_right_panel()` 并列
- 每种板件独立 View3D 刷新路径
- UI 内 `if face == LEFT` 硬编码

---

## 参考

- 管线详图：`docs/PANEL_ADD_PIPELINE.md`
- 分层总览：`docs/ARCHITECTURE.md`
