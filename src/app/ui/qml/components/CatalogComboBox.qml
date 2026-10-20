import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Model picker with per-provider accordion sections. The catalog is a flat list
// whose provider headers are collapsible; selecting a model calls back into the
// job form with the entry index so provider/model resolution stays in Python.
Button {
    id: root

    property bool vision: false
    // provider id -> true when its section is collapsed
    property var collapsed: ({})

    readonly property var entries: root.vision ? jobForm.visionEntries : jobForm.analysisEntries
    readonly property string currentModel: root.vision
                                             ? jobForm.visionModelText
                                             : jobForm.analysisModelText

    text: root.currentModel.length > 0 ? root.currentModel : qsTr("Select a model")
    enabled: root.vision ? jobForm.visionModelEnabled : jobForm.analysisModelEnabled
    font.pixelSize: Theme.fontSizeSmall
    implicitHeight: Theme.controlHeight

    contentItem: Text {
        text: root.text
        font: root.font
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
        leftPadding: 8
        rightPadding: 8
        color: root.enabled ? Theme.text : Theme.muted
    }

    background: Rectangle {
        color: Theme.field
        border.color: root.activeFocus || popup.opened ? Theme.primary : Theme.fieldBorder
        radius: 3
    }

    onClicked: popup.opened ? popup.close() : popup.open()

    // Provider of the currently selected model in this dropdown ("" if none).
    function selectedProvider() {
        for (let i = 0; i < root.entries.length; ++i) {
            const e = root.entries[i];
            if (!e.header && e.name === root.currentModel)
                return e.provider;
        }
        return "";
    }

    function sectionCount(provider) {
        let n = 0;
        for (let i = 0; i < root.entries.length; ++i) {
            const e = root.entries[i];
            if (!e.header && e.provider === provider)
                ++n;
        }
        return n;
    }

    // Collapse every section except the selected provider's, so the popup
    // opens focused on the active provider while the rest show a model count.
    function resetCollapsed() {
        const sel = selectedProvider();
        const next = {};
        for (let i = 0; i < root.entries.length; ++i) {
            const e = root.entries[i];
            if (e.header && e.provider !== sel)
                next[e.provider] = true;
        }
        root.collapsed = next;
    }

    Popup {
        id: popup
        y: root.height
        width: root.width
        padding: 1
        implicitHeight: Math.min(list.contentHeight + 2, 360)

        onOpenedChanged: {
            if (opened)
                root.resetCollapsed();
        }

        contentItem: ListView {
            id: list
            clip: true
            model: root.entries
            implicitHeight: contentHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}

            delegate: ItemDelegate {
                id: entry
                required property int index
                required property var modelData
                width: list.width
                font.pixelSize: Theme.fontSizeSmall

                readonly property bool isHeader: modelData.header === true
                readonly property bool collapsedSection: !isHeader
                    && root.collapsed[modelData.provider] === true
                visible: !collapsedSection
                height: collapsedSection ? 0 : implicitHeight

                contentItem: Text {
                    text: {
                        if (!entry.isHeader)
                            return "     " + (entry.modelData.label || "");
                        const isCollapsed = root.collapsed[entry.modelData.provider] === true;
                        const arrow = isCollapsed ? "\u25B6  " : "\u25BC  ";
                        const suffix = isCollapsed ? " (" + root.sectionCount(entry.modelData.provider) + ")" : "";
                        return arrow + (entry.modelData.label || "") + suffix;
                    }
                    font.pixelSize: Theme.fontSizeSmall
                    font.bold: entry.isHeader
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    color: entry.isHeader ? Theme.muted : Theme.text
                }

                background: Rectangle {
                    color: entry.isHeader
                           ? "#eef1f5"
                           : (entry.hovered ? "#e6eef8" : "transparent")
                }

                onClicked: {
                    if (entry.isHeader) {
                        const next = Object.assign({}, root.collapsed)
                        next[entry.modelData.provider] = !(next[entry.modelData.provider] === true)
                        root.collapsed = next
                    } else {
                        if (root.vision)
                            jobForm.selectVisionModel(entry.index)
                        else
                            jobForm.selectAnalysisModel(entry.index)
                        popup.close()
                    }
                }
            }
        }

        background: Rectangle {
            color: Theme.field
            border.color: Theme.border
            radius: 3
        }
    }
}
