# 08. Interactivity, persistence and loading

*Chromium source reading (main `22b3b159`, 2026-10-18, M158; M153 = branch 8010 from `$SP/src/chromium-153`), with
probes run in headless Chromium 153.0.8010.12. Neighbours: [04](04-animations-and-scroll.md) owns SMIL, scroll snap,
scroll anchoring, scroll buttons and markers, and animation triggers. [01](01-lifecycle.md) owns frames and iframes.
[09](09-roadmap.md) is the roadmap.*

## Conventions

- **Paths.** `core/…` and `platform/…` mean `third_party/blink/renderer/{core,platform}/…` at main. `net/`,
  `services/network/` and `content/` files were read from gitiles main on 2026-10-18, marked *(code, gitiles)*. Line
  numbers are main's unless a line says [153].
- **Probes.** Each probe is a page plus a Playwright harness in
  `exp/08/exp/`. They are
  cited as "probe `name`". Network probes use tiny local node servers on `http://localhost`, which counts as a secure
  context for dictionaries. They are marked *(measured)*.
- **Labels.** Every claim is labelled *(code)*, *(measured)*, *(docs)* or *(inference)*.

## Summary

1. **paint can write dictionaries without any frames.** Use a `Speculation-Rules` response header and document rules.
   CSS decides which links are candidates through `display`. A prefetched response carrying `Use-As-Dictionary`
   registers. A link that is hidden and shown again is fetched again. *(measured; §1.9, Idea 1)*
2. **`Clear-Site-Data: "cache"` on any same-origin response erases every dictionary of the origin.** That includes a
   CSS `mask-image`, so a static `/reset` path is a reset primitive that CSS can trigger. *(measured, code)*
3. **An `<object>` that was shown once keeps its frame after `display: none`.** paint's written cells should
   therefore use two frames each, about 960 of the 1,000 allowed per page. *(mechanism measured; paint's count is
   inference from its CSS; `kMaxNumberOfFrames`, `core/page/page.cc:116`)*
4. **The renderer's real request ceiling is 1,350 concurrent requests per process, not 2,700.** The network service
   counts each request twice; the measured result is 1,650 of 3,000 requests rejected. Blink caps one document at
   1,024 in flight, which is why one document "throttles itself". *(measured, code)*
5. **Fewer requests in flight should stop the HTTP/2 `GOAWAY` losses.** The losses are bounded by the length of
   `SpdySession`'s pending queue. Main doesn't fix the race. Keeping in-flight requests at or below the server's
   stream limit should avoid it. The HTTP/3 part of paint's docs is wrong: in-flight requests are retried over TCP;
   only queued ones fail. *(code; inference for the remedy)*
6. **`<input pattern>` runs V8's irregexp** in a private per-isolate context, whether or not the page has script. It
   compiles `^(?:p)$` with the `v` flag, caps backtracking at 1,000,000 and evaluates lazily on the next style recalc.
   But each control yields one bit, and `<textarea>` has no `pattern`, so it can't replace js-minus-js's lexer.
   *(code, measured)*
7. **New script-free input channels, all measured in 153:**
   - the slider thumb as an anchor (`::-webkit-slider-thumb { anchor-name }`), which tracks keys, mouse and touch;
   - select type-ahead as a key decoder;
   - `field-sizing: content` inputs, whose width equals the typed text's advance;
   - arrow keys on a focused snap scroller, one snap step per press;
   - radio-group arrows, which wrap;
   - `focusgroup`;
   - `accesskey`, which clicks even a `display: none` checkbox;
   - `interestfor`, with CSS-timed hover delays and a long-press on touch.
8. **`<link rel=compression-dictionary>` waits for main-thread idle, not network idle.** It is an idle callback with
   no timeout. Main-thread work during probing, not the network, delays paint's undo write. *(code)*
9. **Nothing on main changes ENGINE_NOTES 44–49.** The editing commands are unchanged and `white-space-collapse` still
   has no `preserve-spaces`. *(code)*
10. **The commands a button can run without flags are popover and dialog commands only.** `step-up`/`step-down`,
    `toggle`/`open` for `<details>` and `show-picker` sit behind `HTMLCommandActionsV2`, at status "test" from 153
    through main. The scroll commands are "experimental". *(code)*

---

## 1. How it works

### 1.1 From a user action to a CSS-visible bit

```
 browser ──IPC──▶ MainThreadEventQueue ──▶ WebFrameWidgetImpl ──▶ EventHandler
                  (mousemove/wheel/touchmove     │                  ├ MouseEventManager   (:hover, :active)
                   coalesced, run at the start   │                  ├ PointerEventManager (interestfor, light dismiss)
                   of BeginMainFrame; keys,      │                  ├ GestureManager      (touch :active/:hover)
                   clicks run as soon as queued) │                  └ KeyboardEventManager (accesskey, Tab, arrows)
                                                 ▼
             default event handlers change one of three stores:
               a. DOM attributes            open (details, dialog), hidden=until-found
               b. element-internal state    checkedness, dirty value, selectedness, validity, popover visibility,
                                            interest state, select popup, scroll offset
               c. UserActionElementSet      hover, active, focus flags (transient, per document)
                                                 ▼
             Element::PseudoStateChanged(kPseudoX) → invalidation sets → restyle in the next lifecycle update
```

**When events run** *(code)*
- `MainThreadEventQueue::IsRafAlignedEvent` (`platform/widget/input/main_thread_event_queue.cc:890-909`) delays only
  mouse move, wheel and touch move until the next frame.
- Key, button and click events are dispatched on arrival. A discrete action therefore becomes visible in the next
  frame's style and layout, with no extra frame of latency.
- Timers add delay: interest delays (default 0.25 s and 0.15 s), select type-ahead (1 s window), spin-button
  auto-repeat (theme delays) and idle tasks (`<link rel=compression-dictionary>`, §1.9).

**Hover follows layout** *(code)*
- Every layout ends with `MarkHoverStateDirty()` (`core/frame/local_frame_view.cc:2006`).
- `WebFrameWidgetImpl::BeginMainFrame` then hit-tests the last mouse position before anything else
  (`core/frame/web_frame_widget_impl.cc:3064-3070`).
- So `:hover` tracks content moving under a still mouse, one frame late. It costs one hit test per frame after any
  layout, whenever the mouse is over the page. *(inference: this is a per-frame cost that css-physics pays while the
  mouse rests on its 3D scene; unmeasured.)*
- A precomputed-hover path exists on main (`CompositeHoverStyle`, no status, `crbug.com/571157138`). It is dormant.

**What survives what** *(code)*
- Store (a), DOM attributes, survives nothing except DOM serialization.
- Store (b), internal state, is saved per history item by `FormController`. It is restored only for back/forward and
  session restore (`if (history_item_ && IsBackForwardOrRestore(load_type_))`, `core/loader/document_loader.cc:2297`),
  not on reload.
- Store (c), the user-action flags, is transient.

#### Table 1. Script-free state changes

| User action | Markup | State | CSS reads it with | 153 |
|---|---|---|---|---|
| click, Space, `accesskey`, label click | checkbox / radio | checkedness; radios exclusive per name | `:checked`, `:indeterminate` | yes |
| arrow keys on a focused radio | radio group | next radio checked, wraps | `:checked` | yes *(measured)* |
| click `<summary>` | `<details name=g>` | `open`, exclusive within `g`, all closable | `[open]`, `:open` | yes |
| click `button[commandfor][command=toggle-popover\|show-popover\|hide-popover]`, `[popovertarget]` | `[popover=auto\|manual\|hint]` | showing | `:popover-open` | yes |
| click `button[command=show-modal\|close\|request-close]` | `<dialog closedby=any\|closerequest\|none>` | `open`, modal flag | `[open]`, `:open`, `:modal` | yes |
| hover for `interest-delay-start`, keyboard focus, long-press on a button | `[interestfor=id]` | interest state | `:interest-source`, `:interest-target` | yes *(measured)* |
| click `<a href=#id>` | target element | document's CSS target, history entry | `:target` | yes |
| Tab, click, `focusgroup` arrows, `accesskey` | focusables | focus | `:focus`, `:focus-visible`, `:focus-within` | yes *(measured focusgroup)* |
| typing | `<input>`, `<textarea>` | dirty value, validity | `:placeholder-shown`, `:valid`/`:invalid`, `:in-range`/`:out-of-range`, `:user-valid`/`:user-invalid` (after blur); width under `field-sizing: content` | yes *(measured)* |
| ↑/↓, spin buttons, wheel while focused | `input[type=number]` | value ± step, clamped | as above, plus text width | yes *(measured)* |
| printable keys on a focused select | `<select>` | selected option by prefix | `option:checked`, `:has()`, `<selectedcontent>` clone | yes *(measured)* |
| drag, arrows, touch | `input[type=range]` | value | thumb position via `anchor-name` on `::-webkit-slider-thumb` | yes *(measured)* |
| arrows, PageUp/PageDown, Home/End, Space on a focused scroller | scroll container | scroll offset, snap-aware | scroll/view timelines, `scroll-state()` (chapter 04) | yes *(measured)* |
| mouse over / press | any | user-action flags | `:hover`, `:active` | yes |
| drop text on an editable | `<input>`, `<textarea>`, contenteditable | value / DOM | as typing | yes *(code)* |

### 1.2 Invokers, interest, popovers, dialogs, details

**Which commands parse** *(code)*
- `HTMLElement::GetCommandEventType` (`core/html/html_element.cc:3506-3628`) parses `command`. Without flags it
  accepts:
  - `toggle-popover`, `show-popover`, `hide-popover`;
  - `show-modal`, `close`, `request-close`;
  - custom `--names`, which only dispatch a `command` event and so need script.
- Overscroll commands need `OverscrollAreas` (experimental, an origin trial) (:3541).
- Everything below line 3555 needs `HTMLCommandActionsV2`: `show-picker`, `step-up`/`step-down`, fullscreen,
  `toggle`/`open` for details, and media. It is `status: "test"` in 153, 155, 157 and main, so it isn't shipped
  anywhere.
- The scroll commands (`page-up` … `page-inline-end`, :3607) need `HTMLCommandForScrollCommands`, which is
  experimental.
- Invokers are `<button>`s that aren't form submit buttons (`html_button_element.cc:207-209`) and `<menuitem>`.
- **Upshot:** a script-free button can flip popovers and dialogs. A number input can only be stepped from the keyboard
  or its own spin buttons, and a `<details>` only through its summary.

**Popovers** *(code)*
- `ShowPopoverInternal` is at `html_element.cc:1941`; `:popover-open` is invalidated at :2180 and :2777.
- `auto` popovers form a stack: opening one closes unrelated autos, so siblings behave like radios with a "none"
  state. `hint` closes other hints only.
- Light dismiss: `HandlePopoverLightDismiss` (:3165). Since 155 `LightDismissFromClick` is stable and dismissal runs
  on `click` instead of pointerdown/pointerup (`pointer_event_manager.cc:179-200`). A touch drag that starts outside
  an open popover no longer closes it, because a drag makes no click.

**Dialogs and details** *(code)*
- `<dialog closedby>` (`html_dialog_element.cc:240-253`):
  - `any` means light dismiss plus Esc;
  - `closerequest` means Esc only;
  - `none` means neither;
  - the default is `closerequest` for modal dialogs and `none` otherwise.
- `<details name>` groups (`html_details_element.cc:276` `OtherElementsInNameGroup`): opening one closes the others.
- `:open` matches `[open]` on details and dialog, a visible select picker, and an open input picker
  (`selector_checker.cc:3023-3040`).

**Interest invokers** *(code; measured in 153)*

| Trigger | Delay | Code |
|---|---|---|
| `pointerover`/`pointerout`, **not from touch** | `interest-delay-start` / `interest-delay-end`, default 0.25 / 0.15 s (`dom/element.h:307-308`); infinity means never | `pointer_event_manager.cc:202-206`; tasks posted on `kMiscPlatformAPI` by `ScheduleInterestGainedTask`/`ScheduleInterestLostTask` (`element.cc:13261-13330`) |
| `focusin`/`focusout`, not touch-sourced | same | `element.cc:2137-2157` |
| `gesturelongpress` on a `<button>` | none: "the long press has a built-in delay" | `element.cc:2185-2209` |

- `:interest-source` matches the invoker and `:interest-target` the target (`selector_checker.cc:2635-2641`).
- The target need not be a popover; a popover target is also shown (`element.cc:2058-2064`).
- **Measured** (probes `input` and `touch`):
  - with `interest-delay-start: 0.5s`, `:interest-source` was still off at 200 ms, on at 700 ms, and off again after
    the mouse left;
  - a synthesized 1.2 s long-press (`Input.synthesizeTapGesture`) on `<button interestfor>` set `:interest-source` and
    opened a `popover=hint`.
- So hover delays are timers configurable in CSS, and a long-press gives touch users a "held" bit that `:active` doesn't.

### 1.3 Forms as computation

#### `pattern`: a regex the engine runs on every edit

**The code path** *(code)*
- `BaseTextInputType::PatternMismatchPerValue` (`core/html/forms/base_text_input_type.cc:102-140`):
  - builds `"^(?:" + pattern + ")$"` (:126) with `UnicodeMode::kUnicodeSets`, the `v` flag (:105);
  - caches the compiled `ScriptRegexp` until the attribute changes;
  - calls `regexp_->Match(value)` (:137).
- `ScriptRegexp` (`platform/bindings/script_regexp.cc`) wraps `v8::RegExp::NewWithBacktrackLimit(…, 1'000'000)` (:39,
  :68) and `Exec`. Both run inside `V8PerIsolateData::EnsureScriptRegexpContext()`, a private context, under
  `ScriptForbiddenScope::AllowUserAgentScript` (:97-102).
- So it is irregexp, V8's regex engine. It never touches the page's script context and runs whether or not the page
  has script.
- Hitting the backtrack limit makes `Exec` fail, so `Match` returns −1 and the control reports a mismatch.
- `email[multiple]` applies the pattern to each comma-separated value (:90-99).

**When it runs** *(code)*
- Each value change calls `ListedElement::SetNeedsValidityCheck` (`listed_element.cc:697-722`). That marks validity
  dirty and calls `PseudoStateChanged` for `:valid`, `:invalid`, `:user-valid` and `:user-invalid` on the control, its
  form and its fieldset ancestors.
- The regex itself runs when the next style recalc asks `IsValidElement()` (:679-692): once per edit, and only if
  some rule depends on validity.

**What CSS sees** *(code + measured, probe `input`)*
- One bit per control: the OR of type mismatch, step mismatch, range, `minlength`/`maxlength`, pattern, missing value,
  bad input and custom error.
- No pseudo-class names the reason.
- `tooLong` and `tooShort` count only user edits (`TooLong` checks `LastChangeWasUserEdit`).
- Measured sequence: empty → `:valid`; `ab` → `:invalid`; `ab1` → `:valid`; `ab1x` → `:invalid`. `:user-invalid`
  turned on only after blur (`html_input_element.cc:2736`).
- `<textarea>` has no `pattern`. A multi-line program can't be matched.

**Can a bank of patterned inputs lex typed text for js-minus-js?**
- No *(code)*. A regex sees only the value of its own control, and nothing script-free copies text from one control
  (or a contenteditable) into another.
- N inputs would need the user to type into N fields. One pattern gives 1 bit per control per edit.
- What remains useful: a single-line field can be validated by an arbitrary regex, backreferences included, with the
  result in `:valid`. That suits "is this REPL line well-formed", not tokenisation.

#### Number and steps *(code + measured)*
- `StepRange` defines step mismatch as (value − base) mod step ≠ 0, in `Decimal` arithmetic. `:in-range` and
  `:out-of-range` come from min/max.
- Keyboard ↑/↓ step and clamp: with `min=0 max=12 step=3 value=6`, ↑ gave 9, then 12, then stayed at 12. Typing
  `121` made it `:out-of-range` and `:invalid`.
- The spin buttons step on mousedown, then auto-repeat (`SpinButtonElement::StartRepeatingTimer`,
  `spin_button_element.cc:200-206`, theme `InitialAutoscrollTimerDelay`/`AutoscrollTimerDelay`). They also respond to
  the wheel while focused (`ShouldSpinButtonRespondToWheelEvents`).
- The value is text in the inner editor, shaped in the author's font. Under `field-sizing: content` the width followed
  it: 24.6 px for "9", 34.3 for "12", 43.9 for "121".

#### Select type-ahead: a keyboard decoder *(code + measured)*
- `HTMLSelectElement::TypeAheadFind` (`html_select_element.cc:1540-1564`) calls `TypeAhead::HandleEvent`
  (`type_ahead.cc:66-127`) on each printable keypress without Ctrl, Alt or Meta.
- The buffer resets after `kTypeAheadTimeout = 1 s` (:42).
- It searches from the option after the selected one for a `DisplayLabel()` that starts with the buffer, ignoring
  case and accents. Repeating one character cycles among the options that start with it. Disabled options are skipped.
- A closed menulist selects directly and fires change. An open base-select popup moves focus instead.
- Measured: typing `q`, then `z` after 1.1 s, selected those options. `#sel:has(option[value=q]:checked)` reacted in
  the same frame.

### 1.4 Text input: inner editor or contenteditable

**The inner editor** *(code)*
- `<input>` and `<textarea>` keep their text in a UA shadow `div`, styled by
  `TextControlInnerEditorElement::CustomStyleForLayoutObject` (`text_control_inner_elements.cc:155-247`). It inherits
  the host's computed style: `font`, `font-feature-settings`, `font-variation-settings` and the rest, so the author's
  GSUB font shapes typed text and FeatureVariations axes reach it.
- Forced on top:
  - `user-modify: read-write-plaintext-only`: one text node, never a `<div>`. Enter in a textarea inserts `\n`.
  - For `<input>`: `white-space: pre`, `overflow: scroll` with `scrollbar-width: none` (the editor is a hidden
    scroller), and `min-width` = caret width, 1 px for a bar caret (:181-192).

**`field-sizing: content`** *(measured)*
- The control's width equals the advance of its text: 1 px empty, 28.91 px for `abc`, 77.06 px for 8 monospace
  characters at 9.633 px.
- So `<input style="field-sizing: content; font-family: F">` turns any string the user types into a layout width, a
  function of the whole string computed by F's GSUB. `anchor-size()` or a size container then reads it, as
  js-minus-js reads spans (ENGINE_NOTES 22, 34).

**contenteditable on main** *(code)*
- The editing commands that produce ENGINE_NOTES 44–46 changed between 153 and main only by `StyleRef()` → `Style()`
  renames: `insert_paragraph_separator_command.cc`, `delete_selection_command.cc`, `insert_line_break_command.cc`.
- `white-space-collapse` keywords are still `collapse | preserve | preserve-breaks | break-spaces`, in a 2-bit field
  (`core/css/css_properties.json5:8190-8196`). **`preserve-spaces` remains unsupported on main** (ENGINE_NOTES 48).
- Other editing changes since 153 (§3) are bug fixes and kill switches, nothing an editor gains from.

**Selection** *(code)*
- `::selection`, `::search-text` (find-in-page, stable on main) and `::highlight()` are paint-only highlight
  pseudo-elements; no layout reads them.
- `::highlight()` needs the script `Highlight` registry.

### 1.5 Select, range, meter and progress, and UA parts as anchors

**Customizable select** *(code + measured)*
- With `appearance: base-select` (shipped 135), `<selectedcontent>` receives a deep clone of the selected option's
  children on every selection change (`html_selected_content_element.cc`; main tightened the spec behaviour as
  `SelectedcontentSpec2`).
- The clone is styled where it now sits. Probe `input`: `#cs option span { display: inline-block }` stopped applying
  to the cloned span.
- That makes it a script-free DOM copy driven by a user's choice.

**Range thumb** *(measured; code for why)*
- `input::-webkit-slider-thumb { anchor-name: --th }` in the document's stylesheet makes the UA shadow thumb an anchor
  that document elements can reach. The declaration's tree scope is the document.
- `left: anchor(--th left)` on a sibling followed the thumb:
  - 85.19 → 90.88 px after two → presses (value 30 → 32);
  - 232.9 px after a mouse drag (value 82);
  - live during a CDP touch drag (value 10 → 61; probe `touch`).
- `SliderContainerElement` handles touch itself, so the drag works without the gesture-recognizer problems in
  css-physics HISTORY "Touch"; `:active` is still never set for touch.
- `appearance: base` for range (`AppearanceBase`) is experimental in every version.
- *(inference)* The same author-side `anchor-name` should work on any UA part with its own box:
  `::-webkit-inner-spin-button`, `::file-selector-button`, the `::-webkit-datetime-edit-*-field`s of
  date and time inputs (whose fields wrap under ↑/↓, a multi-digit modular counter). Only the thumb was tested.

**Meter and progress** *(code)*
- Their values come only from attributes, so they take no input.

### 1.6 Keyboard

**`accesskey`** *(code + measured, probe `ak`)*
- `KeyboardEventManager::HandleAccessKey` (`keyboard_event_manager.cc:203-224`) runs on char events
  (`web_frame_widget_impl.cc:1435-1441`), or on keydown on platforms that send combined key-downs (:343-352).
- Modifiers: Alt on Linux and Windows, Ctrl+Alt on Mac (`keyboard_event_manager.h:31-37`); Shift is ignored.
- The target is `TreeScope::GetElementByAccessKey` (`tree_scope.cc:892-907`): the **last** element in tree order whose
  attribute matches, case-insensitively, shadow roots included. It walks the whole DOM on every press and **never
  checks rendering**.
- The action is focus, then `AccessKeyAction`, which for most elements is a simulated click (`html_element.cc:3747`):
  - checkboxes and radios toggle;
  - links navigate;
  - command buttons run;
  - `<summary>` toggles its details;
  - an option becomes selected (`SelectOptionByAccessKey`);
  - a textarea is only focused.
- Measured with CDP char events and Alt:
  - a `display: none` checkbox toggled;
  - `<a href=#x>` set `:target`;
  - `button[commandfor][command=toggle-popover]` opened its popover;
  - `<summary>` opened its details. One run in a busier page didn't open it; isolated reruns did.

**Tab, `focusgroup` and radios** *(code + measured)*
- Tab: `FocusController::AdvanceFocus` (`keyboard_event_manager.cc:574-615`) sets `:focus`, plus `:focus-visible` for
  keyboard focus.
- `focusgroup` is stable in 153, 155 and main. Arrow keys move focus among its items, and `wrap` cycles. The handler
  runs before scrolling (`FocusgroupController::HandleKeyboardEvent`, :535). Measured: f0 → f1, then f0 again after
  two more presses.
- Radio groups: arrows move and check, wrapping (`RadioInputType::HandleKeydownEvent`, `radio_input_type.cc:117-170`).
  Measured: g1 → g2 → g3 → g0. That is a counter mod N driven by arrow keys, readable as `:checked`.

**Keyboard scrolling** *(code)*
- `DefaultNavigationKeyEventHandler` (:526-572) maps keys to a direction and granularity, then calls
  `ScrollManager::LogicalScroll` (`scroll_manager.cc:194-…`).
- The start node is the focused element, else the last mouse-press node, else the root. The scroll chain is walked
  from there.
- Snap-aware:
  - arrows call `SnapForDirection`, which moves to the next snap position;
  - Page keys call `SnapForPageScroll`;
  - Home/End call `SnapForDocumentScroll` (:242-262).
- Without snap an arrow moves `kPixelsPerLineStep = 40` px. A page moves the visible length minus an overlap of up
  to 40 px, and at least 87.5 % of it (`cc/input/scroll_utils.h:20-26`).
- Measured, 10 px snap areas: ↓ 0 → 10 → 20, PageDown 20 → 60.
- Keyboard input therefore arrives as numbers: a focused snap container plus a scroll timeline is an up/down counter,
  and the x axis gives left/right.

**Spatial navigation and `autofocus`** *(code)*
- Spatial navigation (`spatial_navigation_controller.cc`) is a setting, off by default; pages can't enable it.
- `autofocus` only chooses the first focus.

### 1.7 Pointer: mouse, touch, drag, selection

**Touch** *(code)*
- `GestureManager::GetHitTypeForGestureType` (`gesture_manager.cc:96-127`): only `GestureShowPress` and
  `GestureTapUnconfirmed` set `:active` or `:hover`. TapDown, ShortPress, LongPress and TwoFingerTap hit-test
  read-only, and TapCancel releases.
- `LongPressReleasesActiveState` (new, stable from 157) makes the lift after a long-press release `:active` (:111-114).
  In 153 it kept the state.
- This confirms css-physics HISTORY "Touch". The only additions are the long-press-to-interest path (§1.2) and the
  slider (§1.5).

**Drag and drop** *(code)*
- Without script a drop does something in two cases only:
  - `DragController::ConcludeEditDrag` (`drag_controller.cc:328-332, 635`) inserts dragged text into an editable,
    which changes its value or DOM;
  - a URL or file dropped on a non-editable page opens a **new tab** (`kNavigationPolicyNewForegroundTab`, :334-383),
    not the current frame.
- `:-webkit-drag` is still in the selector table (`css_selector.cc:679`), but no production code calls
  `Node::SetDragged`, so it never matches.

**Navigation inside frames** *(code; paint's write path)*
- A link in an `<object>` or iframe document navigates that frame and adds a session-history entry for it. A same-URL
  navigation is turned into a replacement in the browser (paint CLAUDE.md).

**`:navigation-source`** *(code; stable in 157)*
- It matches the link or form that started an in-progress navigation (`selector_checker.cc:2952-2959`), a transient
  flag in the outgoing document. *(inference: useless here.)*

**Text fragments** *(measured, probe `tf`)*
- `#:~:text=` reveals `hidden=until-found` content and scrolls to it on a browser-initiated navigation.
- A same-document link click carrying the directive did nothing.

### 1.8 State that survives a reload

**Root scroll and history** *(code + measured)*
- `FrameLoader::NeedsHistoryItemRestore` is back/forward, restore or reload (`frame_loader.cc:186-188`).
- So the **root** scroll offset is restored on reload (paint HISTORY §1, 48 bits), while form state is not (§1.1).
- Subframes restore from their history items only on traversal.
- `kRestore` covers session restore after a browser restart.

**`scroll-initial-target`** *(code + measured, probe `sit`)*
- `ScrollableArea::ApplyScrollStart` (`scroll/scrollable_area.cc:489-501`) scrolls instantly to the target.
- It runs again after every scroller layout (`paint_layer_scrollable_area.cc:1165-1167`) until the scroller is
  explicitly scrolled (`scrollable_area.cc:356-358`).
- Measured:
  - a checkbox moving the target moved the root from 1000 to 3000 and a nested scroller from 700 to 1200, with no
    user scroll;
  - after a reload the history restore won (3000), and later target changes no longer moved the root.
- So CSS writes a nested scroller's offset at will until the user scrolls it (chapter 04). The persistent root
  register is CSS-writable only on a fresh load.

**Dictionary store** *(code, gitiles + local)*

*Limits*
- `kDictionaryMaxCountPerNetworkContext = 1000` per profile (`shared_dictionary_constants.h:17`).
- Per top-level site, `cache_max_count_ / 2 = 500` (`shared_dictionary_manager_on_disk.h:187-191`), shared by every
  frame origin under that site.
- 100 MiB per dictionary (`shared_dictionary_constants.cc:14`). In total, min(1 % of disk, 400 MiB), default 300 MiB
  (`content/browser/network/shared_dictionary_util.cc:22-59`).
- `id` is at most 1,024 characters, is echoed as `Dictionary-ID`, and is not part of the key. `type` must be `raw`.
- `ttl` parses only with `kCompressionDictionaryTTL`, which is disabled in 153 and on main.

*Expiry*
- Expiry is freshness + staleness − age. `no-cache` and `no-store` make it 0, which never registers.
- *(inference)* `max-age=0, stale-while-revalidate=N`, or a Last-Modified heuristic, would register.

*Key and replacement*
- The key is (frame_origin, top_frame_site, host, match, match_dest), stored with `INSERT OR REPLACE`. That is the
  replacement paint's writes rely on.
- Opaque-origin and nonce partitions (sandboxed and credentialless frames) have no store at all
  (`net/shared_dictionary/shared_dictionary_isolation_key.cc:34-45`).

*Eviction*
- Per site, when a site goes over 500, the entries with the oldest `last_used_time` go first.
- Globally, when the profile goes over 1,000, a sweep across all sites cuts it down to 900.
- `last_used_time` is refreshed every time a dictionary is *advertised* (`storage_on_disk.cc:217`). So every paint
  read refreshes all of its entries.
- *(inference)* A profile filling up from other sites can evict about 100 of the least recently read entries, paint's
  among them.

*Selection*
- Expired entries are skipped and match-dest is checked.
- A dictionary whose match-dest is specified beats one without, then the longer `match` string wins, then the newer
  fetch (`shared_dictionary_storage.h:126-188`).

*Header check*
- The decoder checks the header before decoding (`shared_dictionary_header_checker_source_stream.cc:21-31`). dcb's
  is 4 magic bytes + the 32-byte hash, 36 bytes.
- **dcz's is 8 bytes (`5e 2a 4d 18 20 00 00 00`) + 32, so 40 bytes.** paint's ARCHITECTURE says 36. `build.py`
  writes 8 + 32 correctly, so only the doc is wrong.
- `kCompressionDictionaryTransportRequireKnownRootCert` is enabled: nothing is advertised unless the certificate chains
  to a known root, or the host is localhost. *(inference: an SPKI-trusted test certificate on any other host name
  reads every cell as blank.)*

*Registration path*
- `CorsURLLoader::OnReceiveResponse` calls `SharedDictionaryStorage::MaybeCreateWriter`
  (`services/network/cors/cors_url_loader.cc:843-890`). Its checks (`shared_dictionary_storage.cc:197-291`):
  - the request mode;
  - `shared_dictionary_writer_enabled`;
  - a secure context;
  - the header parses;
  - expiry > 0;
  - `raw`;
  - a cache check;
  - cookie access;
  - the URLPattern compiles.
- **The network service has no destination check.** paint's list of destinations that register is Blink behaviour:
  decode cancellation, and which loaders run at all.
- Who sets `writer_enabled`:
  - every frame subresource (`FrameFetchContext::PrepareRequest`, `core/loader/frame_fetch_context.cc:435-437`);
  - navigations only when `is_main_frame` (`content/browser/loader/navigation_url_loader_impl.cc:640-650`). That is
    why iframe and object documents never register.
- The entry commits only after the body completes and the consumer didn't abort (`shared_dictionary_data_pipe_writer.cc`).
  A cancelled image decode therefore loses the write.
- The in-memory map updates asynchronously, after the disk write. *(inference: a probe sent at once may still see the
  old value.)*

*Cache hits*
- The writer refuses a cache-served response only if the *identical* entry is already registered
  (`shared_dictionary_storage.cc:268-274`). An HTTP-cache hit for a different URL does register.
- With `Vary: *` the HTTP cache always revalidates, even under force-cache (`net/http/http_cache_transaction.cc:3233-3242`).
- **So paint's "a cached response never registers" on Back/Forward is Blink's MemoryCache.**
  `DetermineRevalidationPolicyInternal` returns `kUse` for force-cache (`resource_fetcher.cc:2208-2212`) before the
  Vary check (:2269-2271). The request never reaches the network service.

*153 → main*
- Refactors only (`uint64_t` sizes became `std::optional<base::ByteSize>`).
- `kPervasiveSharedDictionaries` was enabled. It covers an unpartitioned store for a configured URL list and is
  irrelevant here.

**`Clear-Site-Data`** *(code + measured, probe `csd`)*
- Dictionaries are cleared when the header asks for `"cache"`, `"cookies"` or `"*"`
  (`browsing_data_remover_impl.cc:702-713`). `"storage"`, `clientHints`, `prefetchCache` and `prerenderCache` don't
  clear them, and `executionContexts` is unrecognised.
- Scope:
  - `"cache"` filters by origin; `"cookies"` by eTLD+1.
  - The network filter ignores partitioning: "TODO(crbug.com/329705715)". It deletes every row whose frame origin,
    top site or dictionary host matches.
- It is honoured on **any** URLLoader with an observer, subresources included
  (`network_service_network_delegate.cc:402-447`), and the response is held until clearing ends.
- It is refused for `LOAD_DO_NOT_SAVE_COOKIES` requests, such as credentials-omit fetches like today's
  `<link rel=compression-dictionary>`. Prefetches have no observer, so a prefetched reset does nothing.
- Measured: after a write, a page with `mask-image: url(/reset.png)` whose response carried
  `Clear-Site-Data: "cache"` made the next probe go out with no `Available-Dictionary`.
- `"cache"` also clears that origin's HTTP cache, preflight cache, bfcache entries, prefetches and prerenders. It does
  not clear the renderer MemoryCache (the origin filter skips `ClearAllResourceCaches`).

**Speculation rules** *(code + measured)*
- The `Speculation-Rules` header is processed for **main frames only** (`speculation_rules_header.cc:47-51`). It is a
  structured-field list of URL strings, each fetched with CORS and same-origin credentials. The response must have
  MIME `application/speculationrules+json` (`core/loader/speculation_rule_loader.cc:62`).
- Inline `<script type=speculationrules>` is dropped when scripts can't run (`script_loader.cc:612`). The header path
  has no such check.
- Document rules (`where: selector_matches`/`href_matches`) skip links with no stored ComputedStyle. That excludes a
  `display: none` inclusive ancestor and display-locked subtrees (`document_speculation_rules.cc:1003-1060`), so
  **CSS chooses the candidates**.
- Links report style gain and loss from `Element::NotifyIfMatchedDocumentRulesSelectorsChanged`
  (`element.cc:6569-6587`).

*Eagerness*
- `moderate` = hover for 200 ms (`anchor_element_interaction_tracker.h:113-114`) or pointerdown.
- `eager` on desktop = hover for 10 ms. `conservative` = pointerdown.

*Limits*
- Prefetch: 50 immediate per page; 2 each for eager, moderate and conservative, first in first out
  (`prefetch_params.h:114-116`).
- Prerender: 10 immediate, 2 others (`prerender_host_registry.h:93-94`).
- The referring page must be visible.

*Registration* (code)
- A same-site prefetch uses the default network context. It is built with
  `CreateResourceRequestForNavigation(is_main_frame=true)`, so `writer_enabled` is true.

*Measured* (probes `spec`, `spec2`, `spec3`, `spec4`, `spec7`)
- The header plus an `immediate` document rule prefetched visible links and skipped one under `display: none`.
- Checking a checkbox that revealed the hidden link prefetched it.
- Hovering a `moderate` link prefetched it after about 200 ms.
- The next probe advertised the hash of the **last prefetched dictionary**, so prefetched responses register and
  replace.
- A link hidden and shown again was fetched again, every time. Duplicate hrefs were fetched once. A `moderate` link
  evicted from the queue was fetched again on re-hover.
- With 60 visible links, 52 were prefetched. Hiding them and showing 60 others prefetched 52 more, and switching back
  52 more: the cap counts candidates that are present at once.
- A candidate hidden 100 ms after it appeared, with the server answering after 400 ms, was requested but **not
  registered**: removing the candidate cancels the prefetch.
- A link whose base `display` is `block` and that an animation hides after 1.5 s (`animation: hide 0s 1.5s forwards`)
  registered.
- An animation can't *show* a candidate: animations don't run on a `display: none` base style.
- `visibility: hidden` and `opacity: 0` links remain candidates.

**bfcache, No-Vary-Search, Early Hints** *(code, gitiles)*
- `kCacheControlNoStoreEnterBackForwardCache` is enabled in 153, 155 and main (level `restore-unless-cookie-change`,
  TTL 3 min), so paint's `no-store` top page can be bfcached.
- Subframe traversals are never bfcache restores (`navigation_controller_impl.cc:3864-3877`). Their subresources use
  `DetermineFrameCacheMode` (`core/loader/frame_fetch_context.cc:177-221`): force-cache before the load event, default
  after.
- `kHttpCacheNoVarySearch` is enabled for all GETs: URLs that differ only in the query can share an entry. No use for
  paint *(inference)*.
- Early Hints still handle only preconnect, preload and modulepreload (`navigation_early_hints_manager.cc:430-462`),
  and a 103 preload has `writer_enabled = false`.

**`:visited` and the HTTP cache** *(code)*
- `:visited` is partitioned (`PartitionVisitedLinkDatabaseWithSelfLinks`, stable). It applies only colours, and
  `:has()` never matches visited state. So it is paint-only persistent state, written by navigating and unreadable by
  layout.
- The HTTP cache is readable only through the dictionary registration rule above, or timing (paint HISTORY §1).

### 1.9 The loader facts paint relies on

**Frames** *(code + measured)*
- `const int kMaxNumberOfFrames = 1000` (`core/page/page.cc:116`). `Page::subframe_count_` is incremented for every
  attached Frame, local or remote (`frame/frame.cc:644`).
- The limit is enforced at creation in `HTMLFrameOwnerElement::LoadOrRedirectSubframe`: `SubframeCount() >=
  MaxNumberOfFrames()` makes it return false silently (`html_frame_owner_element.cc:756-759`).
- Lazy loading is decided after `CreateFrame` (:792), so a `loading=lazy` iframe still takes a frame. That is paint's
  finding, now located.
- An `<object>` creates its frame only from `UpdatePlugin`, which needs a layout object (`html_plugin_element.cc:211-262`),
  so an object that was never shown has no frame.
- But **an object that was shown keeps its frame when hidden**:
  - `DetachLayoutTree` disposes only the view (:305-348);
  - `DisconnectContentFrame` runs only for fallback content or removal (`html_object_element.cc:332`).
- Measured (probe `obj`): 600 objects shown then hidden, plus 600 others shown, gave `window.length = 1000`, the cap.
- Re-showing an object re-navigates it to its `data` URL as a replacement (`html_plugin_element.cc:756`,
  `LoadOrRedirectSubframe(…, true)`). Whatever was painted in that frame is replaced.

**One fetch per URL per document** *(code)*
- Two layers enforce it.
- **The CSS value.** `CSSImageValue::CacheImage` (`css_image_value.cc:160-190`) caches the StyleImage on the value:
  - in 153 a single slot, so a second document that shares a parsed stylesheet reuses the first document's image and
    sends no request;
  - from 157 (`StyleResourceFetcherIdentityCheck`) one slot per `ResourceFetcher`.
  - paint's cell CSS is inline, so this doesn't affect it.
- **The fetcher.** `ResourceFetcher::DetermineRevalidationPolicyInternal` (`resource_fetcher.cc:2125-2330`), for a
  resource already in this document's `cached_resources_map_` (set at :1593):
  - before the load event it reuses any non-raw resource, whatever its headers say (:2230-2245);
  - after it, an image is reused "without cache validation" (:2261-2267) unless it failed, in which case it reloads
    (:2256-2259);
  - `no-store` images are reused too (`kReuseNoStoreImageOnSameSrcReassignment`, enabled, :2214-2228).
- **Another document** finds the resource in the per-process MemoryCache and goes through the Vary, `no-store` and
  freshness checks. `Vary: *` triggers `MustReloadDueToVaryHeader` (:2269-2271): the code behind paint's `Vary: *` rule.

**Request limits** *(code + measured)*
- **Blink, per document.** `ResourceLoadScheduler`
  (`platform/loader/fetch/resource_load_scheduler.cc:37-42, 398-424`):
  - 1,024 in flight;
  - "tight" mode, which allows 2 below `kHigh`, until `<body>` is inserted;
  - 3 for a hidden or throttled main frame, 2 for subframes (`frame_resource_fetcher_properties.cc:118-120`);
  - images are throttleable.
- **Network service, per renderer process.** `kMaxOutstandingRequestsPerProcess = 2700`
  (`services/network/network_context.h:1071-1072`, the same in 153), enforced in `URLLoaderFactory` with
  `ERR_INSUFFICIENT_RESOURCES` and never retried.
  - Each request is counted twice, once for the `CorsURLLoader` and once for its inner `URLLoader`.
  - Measured (probe `budget`): 3 same-origin iframes × 1,000 hanging `<img>` gave **1,650 of 3,000** rejected, so
    1,350 accepted. One document with 3,000 gave none: Blink holds it to 1,024, which is 2,048 counts.
- **ResourceScheduler** (6 per host, 10 delayable per client) applies only to HTTP/1.1. It is bypassed for HTTP/2 and
  HTTP/3 except on 3G or slower.
- **HTTP/2 sessions.** `kInitialMaxConcurrentStreams = 100` and `kMaxConcurrentStreamLimit = 256`. Requests past the
  server's limit wait in an unbounded per-priority queue (`net/spdy/spdy_session.cc:1708-1711`).

**HTTP/2 `GOAWAY`** *(code, gitiles main and 8010)*
- The race described in `bugs/README.md` is in the code and unfixed on main:
  - `DeleteStream` calls `ProcessPendingStreamRequests`, which pops max − (active + created) queued requests and posts
    one `CompleteStreamRequest` task each (:1826-1846, with jgraettinger's "this post can race" TODO).
  - A `GOAWAY` parsed in the same read-loop task (which yields after 32 KiB or 20 ms) runs `StartGoingAway`. That
    refuses only the still-queued requests, which are retried as REFUSED_STREAM, at most 2 times (:1365-1386).
  - The posted tasks then meet `STATE_GOING_AWAY`. `TryCreateStream` returns `ERR_FAILED` (:1684-1685), which
    `HttpNetworkTransaction::GetRetryReasonForIOError` doesn't retry.
- **Why it is hundreds** *(inference from the code)*:
  - `ProcessPendingStreamRequests` doesn't count requests already popped. k streams closing in one task pop
    1 + 2 + … + k = k(k+1)/2 requests; for k = 20–30 that is 210–465, the 200–500 paint saw, in one contiguous run.
  - The losses can't exceed the length of the queue.
- Main's only change to that function is an early return when the session isn't available (`b15c96ac1c76`,
  2026-10-06). The tasks are posted while the session is still available, so it doesn't fix the race.

**HTTP/3 close** *(code, gitiles)*
- `QuicChromiumClientSession::OnConnectionClosed` closes open streams. Those requests get `ERR_QUIC_PROTOCOL_ERROR`,
  which is **retried over TCP** when no headers had arrived. That successful retry is what marks HTTP/3 broken
  (`http_network_transaction.cc:1846-1854, 2302-2333`).
- Requests still waiting for a stream get `ERR_CONNECTION_CLOSED`. Because `IsConnectionReused()` is false for a
  request that never had a stream, they are not retried.
- So paint's "the HTTP/3 close fails everything in flight" (ARCHITECTURE, HISTORY §6) is wrong. As with HTTP/2, the
  queued requests are what is lost.

**`<link rel=compression-dictionary>`** *(code)*
- `PreloadHelper::FetchCompressionDictionaryIfNeeded` (`preload_helper.cc:1038-1090`) registers a
  `LoadDictionaryWhenIdleTask` (:75-103) with `ScriptedIdleTaskController` and **no timeout**. It is a
  `requestIdleCallback` on the document's window.
- It fires in a main-thread idle period, not when the network is idle. Cell documents share the top page's main
  thread, so while probes arrive and the top page restyles and lays out every frame there are few idle periods. That
  is paint's "about 30 s while probing".
- Still cors and credentials-omit on main: the `CDTNew*` flags are experimental.
- Since 157, `kRestrictLinkHeaderOnSubresource` is enabled: `Link: rel=compression-dictionary` on *subresource*
  responses is ignored. Document `Link` headers and `<link>` elements are unaffected, and paint uses neither header.

---

## 2. What it means for the projects

### js-minus-js

**1. Run-time input devices**
- Running programs can't read the keyboard today. Each of these is script-free and measured in 153:
  - **A d-pad.** A focused snap scroller is a counter: each ↑/↓ moves one snap area, and Page/Home/End move further
    (§1.6). Read it with a scroll timeline; the CPU already reads view-timeline registers (ENGINE_NOTES 14). The
    caveats: smooth-scroll animation adds about 100–200 ms per press *(inference)*, and the scroller must be focused
    or the last thing clicked.
  - **getchar.** A focused `<select>` with one option per character decodes keys by type-ahead (§1.3). Give each
    character two options (`a`, `a`): repeating a key then alternates between them, so a repeat is still an edge.
    Type-ahead folds case and accents.
  - **A line-input register.** `<input style="field-sizing: content; font-family: F">`: the width is F's GSUB applied to
    the whole typed string (§1.4). A font that zeroes every glyph but the last gives the last key's code. A font that
    parses decimal digits gives a number. Read it with `anchor-size()`, as RAM is read.
  - **A slider** (`::-webkit-slider-thumb { anchor-name }`): a continuous value from mouse, keys or touch (§1.5).
- **Cheapest test:** a 10-line page per device that writes into one RAM cell, then a PRINT loop.

**2. Keyboard shortcuts for Run and Edit** *(measured)*
- `accesskey="r"` on `#run` toggles it with Alt+R (Ctrl+Alt+R on Mac), even if the checkbox is hidden (§1.6).
- It costs one DOM walk per keypress, about N elements, negligible next to a frame.
- Watch for a later element with the same key: the last one in tree order wins.

**3. The editor stays contenteditable**
- Nothing on main fixes ENGINE_NOTES 44–49, and `preserve-spaces` is still missing (§1.4).
- `<textarea>` would avoid notes 44–46 (one text node; Enter inserts `\n`) but takes away per-line elements. The scan
  needs a sentinel per line, and a font can't see across preserved newlines: each `\n` splits the shaping item
  *(inference from LayoutNG's inline item builder)*.
- One `<input>` per line would give per-line widths but breaks Enter and arrow navigation.
- Faster readback stays a font question (PRIMITIVES P11).

**4. `pattern` is no lexer**
- It gives one bit per control (§1.3). At most it could gate Run on a regex over a one-line REPL input.

**5. `<selectedcontent>` copies DOM**
- *(speculation)* A user's choice could select one of N code templates (an option's children) into a fixed place in
  the compiler's character chain. Cheaper than typing an example program; nothing measured beyond the clone.

### css-physics

**1. Hover costs a hit test per frame** *(code; cost unmeasured)*
- Every layout dirties hover, and the next frame hit-tests the mouse position (§1.1).
- With the mouse resting over the scene, every physics frame pays a hit test of a large `preserve-3d` tree and
  possibly a hover-chain restyle. The old `:has(:nth-child(k):hover)` pointer cost about 30 ms per move (HISTORY), and
  part of that may have been this.
- **Test:** trace a frozen 48-body scene with the mouse inside versus outside the viewport.

**2. One-axis controls without the scroll gesture machinery** *(measured)*
- A range slider gives an exact value live during a touch drag, read through the thumb's anchor (§1.5). That suits
  camera yaw, zoom and a gravity knob.
- It doesn't replace the per-body handles: it has one axis and doesn't unproject.

**3. A touch "hold" bit** *(measured, CDP-synthesized)*
- A long-press on `<button interestfor>` gives `:interest-source` at once (§1.2). `:active` for touch needs show-press
  and is cancelled at the slop (HISTORY "Touch").
- For example: long-press a body to pin it.
- **Test** on the Android emulator, since CDP's synthesized gesture skips the real detector.

**4. Keyboard nudges**
- Arrow keys on a focused snap scroller (§1.6), or a radio group per body selected with arrows, give exact integer
  impulses. This needs no new engine work.

### paint

**1. The frame budget is two per written cell** *(mechanism measured; paint's count is inference from its CSS)*
- Each written cell shows `x` while its row is 0 px wide and `p/v` once the value arrives. The `x` frame survives
  being hidden (§1.9).
- So 480 cells use about 960 of the 1,000 frames.
- `build.py`'s 490-cell cap comes from the 500-dictionary limit, and happens to stay just under the frame limit too
  (980 + 1).
- Any design that shows a third `<object>` per cell would run out at about 330 cells. That includes the staged-read
  patch if it switches objects, or a retry row that reads a different value.
- Hiding the blank page with `visibility` instead of `display: none` doesn't help. Removing the element would, but
  that needs script.
- **Fix:** show `x` only once the read has finished and the row is still 0 px wide, gated on the existing
  second-sentinel `--go` flag instead of "row 0 px wide". Written cells then never create the `x` frame, so every cell
  uses one frame. The cost: a blank cell becomes paintable only after the read, about 20–30 s on the live site.
  *(inference)*

**2. The process request budget is 1,350, not 2,700** *(measured)*
- The top page alone holds 1,024 in flight, which is 2,048 of 2,700 counts. That leaves about 325 requests for every
  cell document in the same process.
- The cell documents load *during* probing: each `p/v` page writes its own value again through `mask-image` on load.
  *(inference)* Some of those 480 writes, and any write from a paint made while probes are in flight, are rejected
  with `ERR_INSUFFICIENT_RESOURCES` and never retried.
- The redundant ones are harmless, and the idle `<link>` write backs up the real ones.
- Dropping the start page's `mask-image` (HISTORY "fewer requests per load") also removes this pressure.

**3. `GOAWAY` losses come from the queue, so don't build a queue** *(code; remedy is inference)*
- With Blink at 1,024 in flight and the server allowing about 100, roughly 900 requests sit in `SpdySession`'s pending
  queue. That queue is what the race drains with `ERR_FAILED` (§1.9).
- Staggered reads that keep no more than about the server's `SETTINGS_MAX_CONCURRENT_STREAMS` in flight leave the
  queue empty. The `GOAWAY` then only refuses streams above `last_stream_id`, which are retried.
- The completion test from the staged-reads patch (`<img>` pending/failed/hit sizes, PRIMITIVES finding 6) can gate
  each stage.
- The cost is one round trip per stage, about 90 stages × RTT at 100 per stage. *(inference)* That would make the
  retry row and its 7,680 extra probes for a blank canvas unnecessary.
- **Test:** a staged build under `serve.js --goaway 2000` (HTTP/2) and `make test-goaway`.

**4. Corrections to paint's docs** *(code)*
- The HTTP/3 close: in-flight requests are retried over TCP (and that retry marks HTTP/3 broken); queued ones are lost.
- The dcz header is 40 bytes, not 36.
- The link write waits for main-thread idle, not network idle.
- "A cached response never registers" is Blink's MemoryCache, not the store. An HTTP-cache hit can register.
- The ~7,700 failure is 2,700 counts at two per request.
- "A hidden `<object>` takes none" holds only for one that was never shown.

**5. A background tab loads very slowly** *(code)*
- A hidden page's main frame gets 3 requests in flight (§1.9). A canvas opened in a background tab reads at roughly
  RTT/3 per probe, about 9,000 × 30 ms / 3 ≈ 90 s, until it is shown. *(inference)*

**6. Reads refresh the store** *(code)*
- Every probe that advertises a dictionary bumps its `last_used_time`. A canvas that is read regularly is the last
  thing global eviction removes.
- But `workers.dev` previews and other projects on the same site share its 500 (COMPARISON).

**7. A reset button is static** *(measured)*
- A page `/reset` (or a 1 px `mask-image`) whose response sends `Clear-Site-Data: "cache"` wipes the canvas.
- It also clears the origin's HTTP cache and bfcache. Gate it behind a confirm `<dialog>`.
- *(inference)* Cloudflare `_headers` can set it on one path.
- Danger: the same header anywhere on the origin, a preview Worker included, erases every visitor's canvas.

---

## 3. What's changing

Status from `runtime_enabled_features.json5` (153/155/157 from `$SP/src/versions`, main local). Network flags are
from gitiles. "exp" means experimental, behind a flag.

| Feature | 153 | 155 | 157 | main | Effect here |
|---|---|---|---|---|---|
| `ResponsiveIframes` (`frame-sizing`, `<meta name=responsive-embedded-sizing>`) | exp | stable | stable | stable | A child document reports its natural size to its parent `<iframe>` at DOMContentLoaded and load (`document.cc:4416`, :8186), and through `requestResize()` with script. A one-shot child → parent channel; `<iframe>` only (`LayoutIFrame`), not `<object>`. An SVG child reports every frame instead, to `<object>` in any build (01 §1.8). Chapter 01 owns it. |
| `LightDismissFromClick` | exp | stable | stable | stable | Popover/dialog light dismiss on click: drags no longer dismiss |
| `CleanUpActivationBehavior` | — | exp | stable | stable | Activation rework: summary toggling moves to `RunActivationBehavior`, inner-editor text filtering to `FilterBeforeTextInserted`. Re-check accesskey and label behaviour on upgrade |
| `LongPressReleasesActiveState` | — | — | stable | stable | Long-press lift clears `:active` |
| `NavigationSourcePseudoClass` (`:navigation-source`) | — | exp | stable | stable | §1.7 |
| `StyleResourceFetcherIdentityCheck` | — | — | stable | stable | CSS images cached per fetcher (§1.9) |
| `ReadOnlyTextControlSelection`, `FirstLineAndLetterExcludeInputTextarea`, `CaretBlinking`, `TimePickerHonorsStep`, `PopupWidgetRequiresUserActivation`, `InputClientRectWithoutInlinePadding` | — | — | stable | stable | Form/editing fixes; `::first-line`/`::first-letter` stop applying inside text controls |
| `TextOverflowInTextarea` | — | stable | stable | stable | — |
| `SelectedcontentSpec` → `SelectedcontentSpec2` | stable | stable | — | stable (v2) | `<selectedcontent>` spec update |
| `OverscrollGestures` → `OverscrollAreas` (+ overscroll commands) | exp | exp | exp | exp | Not usable |
| `HTMLCommandActionsV2` | test | test | test | test | step/toggle/open/picker commands, unshipped |
| `HTMLCommandForScrollCommands`, `AppearanceBase`, `CustomizableCombobox`, `FilterableSelect`, `FocusgroupV2`, `HTMLInterestForInterestButtonPseudo`, `DialogCloseWhenOpenRemoved` | exp | exp | exp | exp | Watch: `AppearanceBase` would make range/checkbox parts real stylable elements |
| `SequentialFocusPrimitives` | — | — | test | test | — |
| `DragThresholdRequiresMouseMovement` | — | — | — | test | — |
| `CompositeHoverStyle` | — | — | — | no status | Precomputed `:hover` applied on the compositor (`crbug.com/571157138`). If it ships, hover changes may stop costing main-thread restyles |
| `kRestrictLinkHeaderOnSubresource` (blink feature) | off | off | on | on | Link headers on subresource responses ignored |
| `kPervasiveSharedDictionaries` (network) | off | ? | ? | on | Unpartitioned dictionaries for a configured list; no effect |
| `CDTNewCrossOriginHandling` / `CDTNewDestination` / `CDTNewReferrerAndReferrerPolicyHandling` | exp | exp | exp | exp | Dictionary-transport update (chromestatus 4895435813683200, intent to ship M156) still flagged: the link fetch stays cors/omit |
| `net/spdy` | — | — | — | `b15c96ac1c76` | Reentrancy guard; GOAWAY race intact |

**Unchanged, checked** *(code)*
- ENGINE_NOTES 44–49 editing paths.
- `white-space-collapse` keywords.
- Frame limit, `ResourceLoadScheduler` constants, `kMaxOutstandingRequestsPerProcess`.
- The dictionary store's semantics.
- `HttpNetworkTransaction` retry rules.
- QUIC close handling.
- Clear-Site-Data's dictionary clearing.
- Speculation-rules limits.

**Work in progress visible in code**
- `CompositeHoverStyle`.
- `FilterableSelect`/`CustomizableCombobox` (`:active-option`, `:filtered`).
- Overscroll areas with `show-overscroll`/`hide-overscroll` commands and `:overscroll-closed` (new pseudo-class on
  main).
- Scroll commands.
- `PrerenderUntilScript`, an origin trial: prerender only until the first script.

---

## 4. Ideas, ranked by expected value × confidence

**1. paint: write through speculation-rules prefetch and drop the cell `<object>`s for writing**
*(code-backed; core mechanism measured; design untested)*
- The top page sends `Speculation-Rules: "/rules.json"`, with one document rule:
  `{"source":"document","where":{"selector_matches":".w"},"eagerness":"immediate"}`.
- Each cell has 16 radios, visible only for the palette colour, as the cell pages do today. A checked radio makes an
  invisible `<a class=w href="/c/k/d/v.png">` displayed for about 2 s:
  - base `display: block` under `:checked`;
  - `animation: hide 0s 2s forwards` to `display: none`;
  - the radio shows the colour at once.
- The prefetch registers dictionary v for cell k in the top page's own partition. Measured: registration, CSS gating,
  a fetch on every re-show, cancellation if hidden too early, about 50 present at once.
- **Gains:**
  - 0 frames instead of about 960, so more cells: still capped at 490 by the 500-dictionary limit;
  - no per-load cell writes: −480 mask-image and −480 idle-link requests per load, which matters against Cloudflare's
    10,000 per connection;
  - writes leave from the browser process, outside the renderer's 1,350 budget;
  - instant feedback with no navigation.
- **Losses:**
  - Back/Forward undo: radios make no history entries;
  - prefetch needs the page visible and is main-frame only;
  - the paint must stay a candidate until its response completes;
  - a write lost to `GOAWAY` isn't retried *(inference)*;
  - *(inference)* the rules JSON needs MIME `application/speculationrules+json`. Can Cloudflare `_headers` set
    `Content-Type` on a static asset? Unknown.
- Hover-to-paint is the `moderate` variant: a 200 ms dwell, no click.
- **Cheapest test:** a 4×4 selftest site on `serve.js` (add the header and MIME), paint, reload, read back. Then the
  same on a Workers preview.

**2. paint: staggered reads that keep in-flight ≤ the server's stream limit** *(code-backed inference)*
- §2 paint item 3: no SpdySession queue means no `GOAWAY` losses. The retry row, its 7,680 extra probes and the
  sentinels could then go.
- **Test:** a staged build under `serve.js --goaway 2000`, counting `ERR_FAILED` in the net log.

**3. js-minus-js: run-time keyboard and slider devices** *(measured primitives)*
- Snap-scroller d-pad, select getchar, `field-sizing` line input, slider (§2 js-minus-js item 1).
- **Test:** wire one into a RAM cell and run a program that echoes it.

**4. paint: a static reset button with `Clear-Site-Data: "cache"`** *(measured)*
- Behind a `<dialog closedby=any>` confirm, opened by `command=show-modal`.
- **Test:** add `/reset` to `selftest/`.

**5. js-minus-js: `accesskey` for Run and Edit** *(measured)*
- One attribute; Alt+R.

**6. css-physics: measure the per-frame hover hit test** *(code; magnitude unknown)*
- If it is milliseconds, add `pointer-events: none` on the scene except the handles. That shrinks the hit-test tree.
  Or make the overlay take the mouse.

**7. paint: fix the frame accounting in docs and in `build.py`'s assertion** *(measured)*
- `assert 2 * N + 1 <= 1000`, and note that the staged-reads patch must not show a third object.
- Or gate `x` on read completion, so each cell uses one frame (§2 paint item 1).
- **Test:** count `window.length` after a full load in `tools/e2e.js`.

**8. css-physics: slider controls and a long-press "hold"** *(measured, CDP only)*
- Test on the Android emulator (`shared/android/`).

**9. paint: prerender as parallel write documents** *(speculation)*
- Up to 10 immediate prerenders, each a full main-frame document. Its subresources register, and its main response
  could register too.
- They might replace cell documents for bulk writes, such as formatting a save area for js-minus-js.
- Prerenders share the renderer process and so the 1,350 budget *(inference)*.
- **Test:** a prerendered page with a `mask-image` write, then a probe.

**10. Everyone: a CSS → scroll write with `scroll-initial-target`** *(measured)*
- A nested scroller's offset follows whichever element CSS makes the target, on every layout, until the user scrolls
  it (§1.8). That is a second way, besides snap, to turn style into a scroll-timeline value. See chapter 04 for costs.

**11. js-minus-js: templates by `<selectedcontent>`** *(speculation)*
- §2 js-minus-js item 5.

**12. Text-fragment search as compute** *(speculation, low)*
- `#:~:text=` reveals `hidden=until-found` blocks containing a match, on cross-document navigations only (measured).
- It needs a navigation per query; no project need fits.

**Dead ends checked** *(code or measured)*
- No `pattern` lexer (§1.3).
- No `step-up` buttons without flags (§1.2).
- `:visited` is unreadable by layout.
- Early Hints can't write dictionaries.
- No-Vary-Search doesn't help: `Vary: *` already forces the network.
- `:-webkit-drag` never matches.
- Drops never navigate the current frame.
- A prefetched `/reset` doesn't clear.
- Animations can't make a `display: none` link a candidate.

---

## 5. Possible bugs and open questions

**Possible bugs**
- **HTTP/3: requests waiting for a stream are never retried** *(code, gitiles)*.
  - Pending stream requests get `ERR_CONNECTION_CLOSED` from `CancelAllRequests`
    (`quic_chromium_client_session.cc:2328`). The retry path requires `IsConnectionReused()`, false for a request that
    never had a stream (`quic_http_stream.cc:259-260`).
  - RFC 9114 §5.2 allows retrying requests the server never processed. It is the HTTP/3 twin of the HTTP/2 race in
    `bugs/README.md`.
  - Unverified against a net log: paint's HTTP/3 logs should show `ERR_CONNECTION_CLOSED` for the lost probes and
    `ERR_QUIC_PROTOCOL_ERROR` retries for the others.
- **HTTP/2: the k(k+1)/2 over-pop** adds to the known report. `ProcessPendingStreamRequests` doesn't account for
  requests it already posted (`spdy_session.cc:1826-1846`), so a `GOAWAY` fails more requests than were ever
  "about to start". It is worth adding to crbug 355006326's notes in `bugs/README.md`.
- **`accesskey` ignores rendering** *(code + measured)*. A `display: none` element receives the access key.
  - The HTML spec's processing model ("assigned access key") doesn't obviously exclude non-rendered elements, so this
    may be correct; not filed.
- **One renderer crash, not reproduced.** Five navigations in one tab between speculation-rules pages, while
  prefetches were in flight, crashed the renderer once ("Page crashed"). Two reruns were clean. Likely machine load
  (other agents); noted only.

**Open questions**
- **Cloudflare:** can `_headers` set `Content-Type: application/speculationrules+json`? Does the edge treat
  `Sec-Purpose: prefetch` requests normally? Does `Clear-Site-Data` pass through `_headers` unchanged?
- **Prefetch and `GOAWAY`:** does a prefetch that fails with `ERR_FAILED` ever retry? Prefetches use the browser's
  loader, but the same SpdySession *(inference)*.
- **Prerender:** do its subresources register dictionaries before activation (Idea 9)?
- **The slider's touch path on a real device:** only CDP touch events were used, which skip the gesture recognizer.
- **The cost of the per-frame hover hit test** in css-physics (Idea 6).
- **The `<summary accesskey>` miss:** it failed in one run of probe `ak` and passed in isolated runs. A focus or
  `:target` side effect from earlier keys in the same page? Unexplained.
