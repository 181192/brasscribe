import NotationKit
import ScoreKit
import SwiftUI

/// The music stand (design/music-stand.md): the score alone, in pages, with a persistent band at
/// the top (the position as plain text, and ✕ Leave) and a control layer that hides itself while
/// the music plays, unless assistive technology, the keyboard or a setting needs it.
struct MusicStandView: View {
    @Bindable var model: PracticeModel
    @Bindable var stand: MusicStand
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.accessibilitySwitchControlEnabled) private var switchControl
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.horizontalSizeClass) private var hsize
    @Environment(\.verticalSizeClass) private var vsize
    @AppStorage(StandSettings.keepControlsKey) private var keepControls = false
    @AppStorage(StandSettings.hintKey) private var hintSeen = false
    @AppStorage("singleKeyShortcuts") private var singleKeys = true
    @FocusState private var focus: StandFocus?
    @AccessibilityFocusState private var scoreFocused: Bool
    @State private var showHint = false
    @State private var editRepeat = false
    @State private var screen: CGRect = .zero

    enum StandFocus: Hashable { case score, leave, control(String) }

    private var form: MusicStand.Form {
        #if os(macOS)
        return .wide
        #else
        if UIDevice.current.userInterfaceIdiom == .phone { return vsize == .compact ? .phoneSide : .phoneUpright }
        return hsize == .compact ? .phoneUpright : .wide
        #endif
    }

    private var largerText: Int { typeSize >= .accessibility1 ? 2 : typeSize >= .xxLarge ? 1 : 0 }
    private var highContrast: Bool { contrast == .increased }
    private var focusInLayer: Bool { if case .control = focus { true } else { false } }

    private var autoHides: Bool {
        MusicStand.autoHides(playing: model.isPlaying, voiceOver: voiceOver || LaunchOptions.standAssistive,
                             switchControl: switchControl || StandSystem.switchControlRunning,
                             fullKeyboardAccess: StandSystem.keyboardNeedsControls, focusInLayer: focusInLayer, keepVisible: keepControls)
    }

    /// The layer is never hidden while something needs it.
    private var layerVisible: Bool { stand.layerShown || !canHide }
    private var canHide: Bool {
        !(voiceOver || LaunchOptions.standAssistive || switchControl || keepControls)
    }

    var body: some View {
        VStack(spacing: 0) {
            topBand
            GeometryReader { geo in
                music(geo.size)
                    .onAppear { apply(geo.size) }
                    .onChange(of: geo.size) { _, s in apply(s) }
            }
        }
        .overlay(alignment: .bottom) {
            if layerVisible {
                layerCard
                    .transition(.opacity)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height + Space.s3 } action: { stand.obscured = $0 }
                    .onDisappear { stand.obscured = 0 }
            } else if showHint {
                hint
            }
        }
        .animation(BrasscribeDesign.Motion.animation(BrasscribeDesign.Motion.base, reduceMotion: reduceMotion), value: layerVisible)
        .background(Color.Brasscribe.bg.ignoresSafeArea())
        .background { keys }
        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { screen = $0 }
        .onChange(of: model.layoutVersion) { _, _ in stand.reset(model) }
        .onChange(of: focus) { _, f in
            // Tab (or any focus move into the band or the layer) shows the layer
            if let f, f != .score { stand.layerShown = true; stand.interaction += 1 }
        }
        .task(id: HideTimer(interaction: stand.interaction, playing: model.isPlaying, shown: stand.layerShown, hides: autoHides)) {
            guard stand.layerShown, autoHides else { return }
            try? await Task.sleep(for: MusicStand.hideAfter)
            guard !Task.isCancelled, autoHides else { return }
            hideLayer()
        }
        .sheet(isPresented: $editRepeat) { RepeatSheet(model: model) }
        // the stand itself takes keyboard focus (like the score screen), so the page keys reach it
        .focusable()
        .focusEffectDisabled()
        .focused($focus, equals: .score)
        // page turners send arrows or Page Up / Page Down (§7); after .focused, so the focused stand gets them
        .onKeyPress(keys: [.rightArrow, .downArrow, .pageDown, .leftArrow, .upArrow, .pageUp, .home, .end]) { press in
            if press.modifiers.contains(.option) {
                if press.key == .downArrow { model.nextBar(); return .handled }
                if press.key == .upArrow { model.previousBar(); return .handled }
                return .ignored
            }
            guard press.modifiers.isEmpty else { return .ignored }
            switch press.key {
            case .rightArrow, .downArrow, .pageDown: stand.nextPage(model)
            case .leftArrow, .upArrow, .pageUp: stand.previousPage(model)
            case .home: stand.turn(to: 0, model, byPlayer: true)
            default: stand.turn(to: Int.max, model, byPlayer: true)
            }
            return .handled
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Music stand"))
        .accessibilityAction(.escape) { leave() }
        .accessibilityIdentifier("musicStandView")
        .focusedSceneValue(\.practice, model)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
        .statusBarHidden(true)
        .persistentSystemOverlays(.hidden)
        #else
        .toolbar(.hidden, for: .windowToolbar)
        #endif
        .onAppear {
            StandSystem.keepAwake(true)
            app.standOpen = true
            focus = .score
            scoreFocused = true
            // once the stand is on screen and focusable, it takes keyboard focus from the opener
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { if focus == nil || focus == .score { focus = nil; focus = .score } }
        }
        .onDisappear {
            // however the stand goes (Leave, or the sidebar opening another screen), the system gets its own behaviour back
            StandSystem.keepAwake(false)
            StandSystem.lockRotation(false)
            app.standOpen = false
            if model.stand === stand { model.leaveStand() }
        }
    }

    private struct HideTimer: Equatable { let interaction: Int; let playing: Bool; let shown: Bool; let hides: Bool }

    private func apply(_ size: CGSize) {
        guard size.width > 0, size.height > 0 else { return }
        if stand.setViewport(size, form: form, largerText: largerText) { model.relayout() } else { stand.follow(model, force: true) }
    }

    // MARK: actions

    private func leave() {
        let opener = stand.opener
        StandSystem.lockRotation(false)
        model.leaveStand()
        switch opener {
        case .toolbar: model.focusStandButton = true
        case .library(let id):
            app.focusScoreRow = id
            app.goHome()
        }
    }

    private func toggleLayer() {
        if showHint { showHint = false }
        if layerVisible { if canHide { hideLayer() } } else { stand.layerShown = true; stand.interaction += 1 }
    }

    /// Hide the layer; focus inside it moves to the score first, so it never lands on nothing.
    private func hideLayer() {
        guard canHide else { return }
        if focusInLayer { focus = .score }
        stand.layerShown = false
        if !hintSeen { hintSeen = true; showHint = true }
    }

    private func touched() { stand.interaction += 1 }

    private func swipe(_ v: DragGesture.Value) {
        let dx = v.translation.width, dy = v.translation.height
        guard abs(dx) > 50, abs(dx) > abs(dy) * 1.5 else { return }
        // within 24 pt of an edge the swipe belongs to the system
        guard v.startLocation.x >= screen.minX + 24, v.startLocation.x <= screen.maxX - 24 else { return }
        if dx < 0 { stand.nextPage(model) } else { stand.previousPage(model) }
        touched()
    }

    // MARK: the music

    @ViewBuilder private func music(_ size: CGSize) -> some View {
        let shown = stand.shown(model)
        ZStack {
            HStack(alignment: .top, spacing: Space.s4) {
                ForEach(shown, id: \.self) { p in
                    StandPageView(model: model, window: stand.window(page: p, model), framed: stand.twoUp, maxHeight: size.height)
                }
            }
            .padding(.horizontal, stand.twoUp ? Space.s4 : 0)
            .frame(width: size.width, height: size.height, alignment: .top)
            .id(stand.pageIndex)
            .transition(.opacity)
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.2), value: stand.pageIndex)
        .frame(width: size.width, height: size.height)
        .clipped()
        .overlay { if model.pages.isEmpty { ProgressView(String(localized: "Laying out the pages…")) } }
        .contentShape(Rectangle())
        .onTapGesture { toggleLayer() }
        .gesture(DragGesture(minimumDistance: 24, coordinateSpace: .global).onEnded(swipe))
        .accessibilityElement()
        .accessibilityLabel(Text("Score"))
        .accessibilityValue(Text("\(stand.partLine(model)), bar \(model.currentBar + 1) of \(model.score.measures.count), \(stand.pageText(model))"))
        .accessibilityAddTraits(.updatesFrequently)
        .accessibilityAction(named: Text("Next page")) { stand.nextPage(model) }
        .accessibilityAction(named: Text("Previous page")) { stand.previousPage(model) }
        .accessibilityAction(named: Text("Next bar")) { model.nextBar() }
        .accessibilityAction(named: Text("Previous bar")) { model.previousBar() }
        .accessibilityAction(named: Text("Play this bar")) { if !model.isPlaying { model.togglePlay() } }
        .accessibilityScrollAction { edge in
            switch edge {
            case .bottom, .trailing: stand.nextPage(model)
            default: stand.previousPage(model)
            }
        }
        .accessibilityFocused($scoreFocused)
        .accessibilityIdentifier("standScore")
    }

    // MARK: the persistent band

    private var positionText: String {
        let bar = model.currentBar + 1
        switch form {
        case .phoneUpright: return String(localized: "Bar \(bar) · \(stand.pageText(model))")
        case .phoneSide: return String(localized: "\(stand.partLine(model)) · bar \(bar) · \(stand.pageText(model))")
        case .wide: return String(localized: "\(model.piece.displayTitle) · \(stand.partLine(model)) · bar \(bar) · \(stand.pageText(model))")
        }
    }

    @ViewBuilder private var topBand: some View {
        HStack(alignment: .center, spacing: Space.s3) {
            Group {
                if form == .phoneUpright {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(stand.partLine(model)).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                        Text(positionText).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                    }
                } else {
                    Text(positionText).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                }
            }
            .monospacedDigit()
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.updatesFrequently)
            .accessibilityIdentifier("standPosition")
            Spacer(minLength: Space.s2)
            if form == .phoneSide, layerVisible {
                onlyMine.fixedSize()
                lockToggle.fixedSize()
            }
            leaveButton
        }
        .padding(.horizontal, form == .phoneUpright ? Space.s5 : Space.s6)
        .padding(.vertical, Space.s2)
    }

    private var leaveButton: some View {
        Button(action: leave) {
            Label("Leave", systemImage: "xmark")
                .font(Font.Brasscribe.label)
                .foregroundStyle(Color.Brasscribe.text)
                .padding(.horizontal, Space.s4)
                .frame(minHeight: 48)
                .background {
                    Capsule().fill(Color.Brasscribe.surfaceRaised)
                        .shadow(color: highContrast ? .clear : .black.opacity(0.08), radius: 3, y: 1)
                        .overlay(Capsule().strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
                }
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .labelStyle(.titleAndIcon)
        .fixedSize()
        .focused($focus, equals: .leave)
        .accessibilityLabel(Text("Leave the music stand"))
        .help(Text("Leave the music stand"))
        .accessibilityIdentifier("standLeave")
    }

    // MARK: the control layer

    @ViewBuilder private var layerCard: some View {
        Group {
            switch form {
            case .phoneUpright:
                VStack(spacing: Space.s3) {
                    transport
                    FlowLayout(spacing: Space.s2) { speed; repeatToggle }
                    if model.myPart != nil || StandSystem.canLockRotation {
                        FlowLayout(spacing: Space.s2) { onlyMine; lockToggle }
                    }
                }
            case .phoneSide:
                FlowLayout(spacing: Space.s4) { transport; speed; repeatToggle }
            case .wide:
                FlowLayout(spacing: Space.s4) { transport; speed; repeatToggle; onlyMine }
            }
        }
        .padding(Space.s4)
        .background {
            RoundedRectangle(cornerRadius: Radius.lg).fill(Color.Brasscribe.surfaceRaised)
                .shadow(color: highContrast ? .clear : .black.opacity(0.08), radius: 6, y: 2)
                .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
        }
        .fixedSize(horizontal: form == .wide, vertical: true)
        .frame(maxWidth: form == .wide ? nil : .infinity)
        .padding(.horizontal, form == .phoneUpright ? Space.s3 : Space.s6)
        .padding(.bottom, Space.s3)
        .simultaneousGesture(TapGesture().onEnded { touched() })
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Music stand controls"))
        .accessibilityIdentifier("standLayer")
    }

    private var transport: some View {
        HStack(spacing: Space.s2) {
            pageButton(next: false)
            iconButton("previousBar", systemImage: BrasscribeIcon.previousBar.systemName, label: Text("Previous bar")) { model.previousBar() }
            Button { model.togglePlay(); touched() } label: {
                Image(systemName: model.isPlaying ? BrasscribeIcon.pause.systemName : BrasscribeIcon.play.systemName)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(Color.Brasscribe.onPrimary)
                    .frame(width: 56, height: 56)
                    .background(Color.Brasscribe.primary, in: Circle())
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .focused($focus, equals: .control("play"))
            .accessibilityLabel(model.isPlaying ? Text("Pause") : Text("Play"))
            .accessibilityIdentifier("standPlay")
            iconButton("nextBar", systemImage: BrasscribeIcon.nextBar.systemName, label: Text("Next bar")) { model.nextBar() }
            pageButton(next: true)
        }
        .foregroundStyle(Color.Brasscribe.text)
        .fixedSize()
    }

    private func pageButton(next: Bool) -> some View {
        let enabled = next ? stand.canGoForward(model) : stand.canGoBack
        return Button { if next { stand.nextPage(model) } else { stand.previousPage(model) }; touched() } label: {
            Image(systemName: next ? "chevron.right" : "chevron.left")
                .font(.body.weight(.semibold))
                .frame(width: 48, height: 48)
                .background(Color.Brasscribe.secondary, in: Circle())
                .overlay { if highContrast { Circle().strokeBorder(Color.Brasscribe.borderStrong) } }
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .opacity(enabled ? 1 : 0.4)
        .disabled(!enabled)
        .focused($focus, equals: .control(next ? "nextPage" : "prevPage"))
        .accessibilityLabel(next ? Text("Next page") : Text("Previous page"))
        .accessibilityIdentifier(next ? "standNextPage" : "standPrevPage")
    }

    private func iconButton(_ id: String, systemImage: String, label: Text, action: @escaping () -> Void) -> some View {
        Button { action(); touched() } label: {
            Image(systemName: systemImage).frame(width: 48, height: 48).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($focus, equals: .control(id))
        .accessibilityLabel(label)
        .accessibilityIdentifier("stand-\(id)")
    }

    /// − Speed 75% +: two steppers around the value, 5 % a step, 25–150 % (2.5.7).
    private var speed: some View {
        HStack(spacing: 0) {
            Button { model.changeSpeed(by: -5); touched() } label: {
                Image(systemName: "minus").frame(width: 48, height: 48).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(model.speedPercent <= 25)
            .focused($focus, equals: .control("slower"))
            .accessibilityLabel(Text("Slower"))
            .accessibilityIdentifier("standSlower")
            Text("Speed \(percentText(model.speedPercent))")
                .font(Font.Brasscribe.label)
                .monospacedDigit()
                .accessibilityIdentifier("standSpeed")
            Button { model.changeSpeed(by: 5); touched() } label: {
                Image(systemName: "plus").frame(width: 48, height: 48).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(model.speedPercent >= 150)
            .focused($focus, equals: .control("faster"))
            .accessibilityLabel(Text("Faster"))
            .accessibilityIdentifier("standFaster")
        }
        .foregroundStyle(Color.Brasscribe.text)
        .frame(minHeight: 48)
        .background(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
        .fixedSize()
        .accessibilityElement(children: .contain)
    }

    /// Repeat the last range; with none set yet, ask for the bars.
    private var repeatToggle: some View {
        let lo = min(model.loopFrom, model.loopTo) + 1, hi = max(model.loopFrom, model.loopTo) + 1
        let title = model.looping ? (lo == hi ? String(localized: "Repeat \(lo)") : String(localized: "Repeat \(lo)–\(hi)")) : String(localized: "Repeat")
        return Toggle(isOn: Binding(get: { model.looping }, set: { on in
            touched()
            if !on { model.setLoop(false) } else if model.loopWasSet { model.setLoop(true) } else { editRepeat = true }
        })) { Label(title, systemImage: BrasscribeIcon.loop.systemName) }
        .toggleStyle(.chip)
        .fixedSize()
        .focused($focus, equals: .control("repeat"))
        .accessibilityIdentifier("standRepeat")
    }

    /// Hidden when there is no part to call yours.
    @ViewBuilder private var onlyMine: some View {
        if model.myPart != nil {
            Toggle(isOn: Binding(get: { stand.onlyMine }, set: { model.setOnlyMine($0); touched() })) { Text("Only my part") }
                .toggleStyle(.chip)
                .fixedSize()
                .focused($focus, equals: .control("onlyMine"))
                .accessibilityIdentifier("standOnlyMine")
        }
    }

    @ViewBuilder private var lockToggle: some View {
        if StandSystem.canLockRotation {
            Toggle(isOn: Binding(get: { stand.rotationLocked }, set: { on in
                stand.rotationLocked = on
                StandSystem.lockRotation(on)
                touched()
                AccessibilityNotifier.announce(on ? String(localized: "Rotation locked. The music stays this way up.")
                                               : String(localized: "The music turns with the phone again."), polite: true)
            })) {
                Label(stand.rotationLocked ? String(localized: "Rotation locked") : String(localized: "Lock rotation"), systemImage: "lock.rotation")
            }
            .toggleStyle(.chip)
            .fixedSize()
            .focused($focus, equals: .control("lock"))
            .accessibilityIdentifier("standLock")
        }
    }

    private var hint: some View {
        Text("Tap the music to show the controls.")
            .font(Font.Brasscribe.callout)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, Space.s4).padding(.vertical, Space.s2)
            .background(Capsule().fill(Color.Brasscribe.surfaceRaised).overlay(Capsule().strokeBorder(Color.Brasscribe.borderStrong)))
            .padding(.bottom, Space.s5)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
            .accessibilityIdentifier("standHint")
    }

    // MARK: keys (§7): leaving and play; the page keys are the onKeyPress above

    private var keys: some View {
        Group {
            key(.escape) { leave() }
            if singleKeys {
                key("f") { leave() }
                #if os(iOS)
                // the Mac's Playback menu has Space
                key(.space) { model.togglePlay(); if !stand.layerShown { stand.layerShown = true; touched() } }
                #endif
            }
        }
        .accessibilityHidden(true)
    }

    private func key(_ k: KeyEquivalent, _ modifiers: EventModifiers = [], _ action: @escaping () -> Void) -> some View {
        Button("", action: action).keyboardShortcut(k, modifiers: modifiers).hidden().frame(width: 0, height: 0)
    }
}

/// One page of the stand: a window onto the long engraved page, drawn at screen size.
private struct StandPageView: View {
    @Bindable var model: PracticeModel
    let window: CGRect
    let framed: Bool
    let maxHeight: CGFloat
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let paint = ScorePaint(model: model, highContrast: contrast == .increased)
        let height = min(window.height, maxHeight - (framed ? Space.s4 : 0))
        Group {
            if let page = model.pages.first {
                Canvas(opaque: false, rendersAsynchronously: false) { ctx, _ in
                    var c = ctx
                    c.translateBy(x: 0, y: -window.minY)
                    paint.draw(page, in: c, visible: window)
                }
                .frame(width: window.width, height: height)
            }
        }
        .padding(.vertical, framed ? Space.s2 : 0)
        .frame(maxWidth: .infinity, alignment: .top)
        .background {
            if framed {
                RoundedRectangle(cornerRadius: Radius.sm).fill(Color.Brasscribe.surfaceRaised)
                    .overlay(RoundedRectangle(cornerRadius: Radius.sm).strokeBorder(Color.Brasscribe.border))
            }
        }
        .accessibilityHidden(true)
    }
}
