# 架构边界（Architecture Boundaries）

本文定义柜体相关代码的**正确分层**与**允许依赖方向**。目标是：`core` 与 `solver` 可脱离 GUI 单测；Qt 仅出现在 **UI** 与 **应用入口** 的装配层。

---

## 分层总览（自上而下）

```
UI (Qt)
   ↓  dispatch(command, …)
CommandDispatcher
   ↓  调用已注册 handler；将 result.events → publish(Event)
commands        ← 纯逻辑编排（无 Qt import；可持有 ctx 闭包以衔接宿主）
   ↓  修改 / 读取领域
core            ← 100% Qt-free 领域（Space / Panel / events 类型与总线实现）
   ↓  输入 Space
solver          ← 纯函数：``solve(space_tree) -> SolveResult``（含 ``panel_list`` / ``events`` 建议；不写 project、不 publish）
   ↑  由 commands 在总线订阅或命令尾部显式调用
event_bus       ← 纯 Python pub/sub（threading；无 QObject / Signal）
   ↓  publish → 订阅回调
UI (render only) ← 板件展示：增量 ``append/remove`` 或全量 ``rebuild_all_display_panels``
```

**板件 Scene 同步**（``cabinet_event_bridge`` → ``SOLVE_COMPLETED``）：

- **全量** ``rebuild all panels``：仅柜体尺寸 Spin（``PANEL_CHANGED`` + ``cabinet_dimensions_spin``）、根布局重算（``new_space_tree``）、``SPACE_CHANGED`` 全量求解链（``full_panel_rebuild``）。
- **增量**：``AddBoardCommand`` / 程序化 ``add_left_panel`` → ``incremental_add_panels`` / ``incremental_remove_panel_ids``。
- 其它求解（如 ``MATERIAL_CHANGED``）只更新 ``project`` 缓存，不触发板件全量 rebuild。

**读作**：用户操作在 **UI** 发生 → 经 **CommandDispatcher** 进入 **commands** → **commands** 读写 **core** 领域数据 → 需要板件列表时调用 **solver**（`Space` → `SolveResult`）→ 领域变更通过 **event_bus** 广播 → **UI** 只做展示更新。

---

## 各层职责与禁区

| 层 | 职责 | 禁止 |
|----|------|------|
| **UI (Qt)** | 控件与 Qt 信号；调用 `CommandDispatcher`；订阅链末端 **仅渲染**。 | 直接 `setattr(project, "root_space", …)`、直接改 `Space` 树（应走 `SET_ROOT_SPACE` 等命令）。 |
| **CommandDispatcher** | 路由命令、合并 payload、`publish` 事件规格。 | 业务规则实现（应落在 `commands` / `core`）。 |
| **commands** | 编排：handler 调 `core`、调 `solver`、把 `SolveResult` 写回 `project`、注册/消费 `event_bus`（桥接在 `cabinet_event_bridge`）。 | `import PySide` / Qt Widgets；不把 OpenGL 写进 `core`。 |
| **core** | `Space` / `Panel` / `events` 等数据结构与纯规则。 | 任何 Qt、任何 `view`/`ui` import、`solver` 内写 `project` 显示字段。 |
| **solver** | ``solve(space_tree) -> SolveResult``；可返回 ``events``（字符串）由 **commands** ``publish``。 | `ctx`、`event_bus`、视图、Qt。 |
| **event_bus** | `subscribe` / `publish`、可选 `set_flush_bridge`（由 **应用入口** 注入宿主调度）。 | `import Qt`；在 core 内绑定 `pyqtSignal`。 |

### 可撤销编辑与 `UndoStack`

- **禁止**在 UI 事件（按钮、菜单、3D 拾取等）中直接调用 `space.add_board`、`space.boards.append`、`split_space`、`remove_board` 等修改领域模型。
- UI **只能** 构造实现 `commands.undo_stack.UndoableCommand` 的命令，再 `undo_stack.push(cmd)`。
- `UndoStack.push` 约定：**内部**先 `command.execute()`，仅当返回真时再入栈；禁止 UI 在 `push` 之外单独 `execute` 同一实例，避免双执行或栈不一致。实现见 `commands/undo_stack.py`。
- 柜体设计模式下的具体命令与快照封装见 `commands/cabinet_edit_command.py`，栈实例挂在 `CabinetDesignView._cabinet_undo_stack`。

**统一交互架构（悬停 → 预览 → 增量场景）**

```
Mouse Move
  → HoverDetector（Main3D / ParamSpace；pick_face_hover_at_screen + FaceType）
  → HoverHitResult（space / face / hit_point；禁止 "left-side" 字符串）
  → CabinetInteractionManager
  → Preview System（preview_spec + preview_manager + preview_renderer）
  → Viewport 重绘 ghost / 盒体 metadata

Click / Shortcut 确认
  → InteractionManager.confirm_viewport_hover_click
  → CommandFactory → UndoStack → AddBoardCommand
  → run_attach_solver_and_publish → finalize_space_mutation（node + face → update_space_topology）
  → SOLVE_COMPLETED（incremental_add_panels）
  → Incremental Scene Update（append/remove；非尺寸/全量 solve 不 rebuild all panels）
```

**空间树变更铁律**：禁止在 handler / UI 零散维护 ``*_neighbor``、``is_occupied``、面占用；一律经 ``SpaceConsistencyManager`` 收尾。

**板件操作空间（remain usable）**：

- 左侧板：在**叶空间**上切掉贴边窄条 → ``occupied_space`` + ``remain_space``（整柜首次可为 root 叶）。
- 右侧板、层板、中竖板等：只作用于 **remaining usable** 叶空间（``core/space/usable_space_resolver.resolve_panel_operating_space``），禁止把已 ``SPLIT`` 的 root 当作「在 root 上放一块板」。
- 命令解析：`resolve_attachment_space``；切分成功后 ``focus_ctx_operating_space`` 将 ``current_space`` 设为新的 ``remain_space``。

- **唯一交互入口**：`CabinetInteractionManager.submit_add_panel(face=…)`（LEFT / RIGHT 共用）。
- **Unified Side Panel System**：`core/panel/side_panel_spec.py` + `solve_side_panel` + `CommandFactory.create_add_panel_command`；详见 `docs/ROLE_DRIVEN_PANEL_ARCHITECTURE.md`。
- **禁止**：Immediate Add、按板件类型复制一套独立添加系统；Viewport 硬编码 ghost、字符串 side 判断。
- **后续板件**（TOP / BOTTOM / SHELF / DIVIDER）：必须 **role-driven** 扩展注册表，不得 `add_top_panel_system` / `add_divider_system` 并列架构。
- **实现模块**：`ui/interaction/hover_detector.py`、`hover_session.py`、`preview_spec.py`、`preview_manager.py`、`preview_renderer.py`；拾取 `view/interaction/hover_pick.py`（``pick_face_hover_*``）。
- **不改**：空间视图轨道旋转、OCC 单击解锁、Ctrl 盒体允许切换、板件添加命令语义。
- 门/抽屉：`create_add_door_command` / `create_add_drawer_command` → `DispatchCabinetEditCommand`。

---

## 与实现文件的对应关系（示例）

- **UI**：`ui/main_window/*`、`view/cabinet_view/*` — Qt 与渲染。
- **CommandDispatcher**：`commands/command_dispatcher.py`。
- **commands 编排**：`commands/ui_commands.py`、`commands/panel_commands.py`、`commands/cabinet_event_bridge.py`（含总线订阅 + `SolveResult` 写回 `project` + 调 `refresh_view` 闭包）。
- **撤销栈**：`commands/undo_stack.py`（`UndoStack` / `UndoableCommand`）；命令工厂：`commands/command_factory.py`；柜体命令：`commands/cabinet_edit_command.py`、`commands/cabinet/add_board_command.py`。
- **core**：`core/space/`、`core/panel/`、`core/events/`。
- **切分**：`core/space/splitter.py` → ``SpaceSplitter`` 仅 **split / 创建子空间**（不写 neighbor、occupancy、faces）。
- **Topological Space Kernel**：`core/space/space_consistency_manager.py` — 任意 split / 加板 / 卸板 / undo / redo / 根尺寸变更 / 求解写回后**必须** ``rebuild_topology(root)`` 或 ``finalize_space_mutation(node=…, ctx=…)``；编排 ``adjacency → occupancy → faces → validate``。``validate`` 默认：父子一致性、非法尺寸、子节点重叠、断裂拓扑（``validators.TOPOLOGY_CHECKS``）。切分用 ``split_space_and_rebuild`` 或 ``rebuild_topology_after_split``。
- **占用语义**：`core/space/space_occupancy.py` — ``rebuild_occupancy`` 唯一写入 ``FREE`` / ``OCCUPIED`` / ``LOCKED``（``metadata.topology_occupancy`` + 同步 ``is_occupied`` / ``is_locked``）；禁止业务层 ``space.is_occupied = True``。
- **Space Face System**：`core/space/space_face_occupancy.py` — ``SpaceFaceOccupancyManager``；``mounted_elements`` 类型：panel / door / drawer / basket / hardware / light / accessory（非 panel **禁止**直挂 ``Space``）。``rebuild_topology`` 末尾统一 ``get_space_face_occupancy_manager().rebuild_faces(root)``。
- **solver**：`solver/cabinet_solver.py` → `core/solver/cabinet_solver.py`。
- **event_bus**：`core/events/event_bus.py`；宿主主线程投递在 `main.py` 通过 `set_flush_bridge` 装配。

---

## 验收提示

仓库内 `arch_check.py` 对部分路径做了静态扫描；**最终以本文件的分层约束为准**。若新增功能，先问：「这段代码属于哪一层？是否把 Qt 或视图塞进了 `core` / `solver`？」
