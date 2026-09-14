import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import "components"

ApplicationWindow {
    id: window

    property bool settingsOpen: false

    width: 1180
    height: 720
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: session.title
    color: Theme.background

    DropArea {
        anchors.fill: parent
        onDropped: (drop) => {
            if (!drop.hasUrls)
                return
            const extensions = [".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".m4a"]
            for (let i = 0; i < drop.urls.length; i++) {
                const local = drop.urls[i].toLocalFile ? drop.urls[i].toLocalFile() : drop.urls[i].toString()
                if (extensions.some((ext) => local.toLowerCase().endsWith(ext))) {
                    session.pendingInput = local
                    break
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 14

        // LEFT: input + tabs
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: window.width * 0.48
            // The hidden StackLayout pages (Batch/History) have wide implicit
            // widths; without this floor the column would exceed its share
            // and overlap the settings column.
            Layout.minimumWidth: 0
            Layout.minimumHeight: 0
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                ComboBox {
                    id: inputCombo
                    Layout.fillWidth: true
                    editable: true
                    model: session.inputPaths
                    textRole: "name"
                    font.pixelSize: Theme.fontSizeSmall

                    property bool syncing: false

                    onActivated: (index) => {
                        syncing = true
                        session.pendingInput = session.inputPaths[index].path
                        syncing = false
                    }
                    onAccepted: {
                        if (editText.length > 0)
                            session.pendingInput = editText
                    }

                    Connections {
                        target: session
                        function onCurrentInputChanged() {
                            const paths = session.inputPaths
                            let found = -1
                            for (let i = 0; i < paths.length; i++) {
                                if (paths[i].path === session.currentInput)
                                    found = i
                            }
                            inputCombo.syncing = true
                            inputCombo.currentIndex = found
                            if (found >= 0)
                                inputCombo.editText = paths[found].name
                            inputCombo.syncing = false
                        }
                    }
                }

                IconButton {
                    glyph: "\uD83D\uDCC2"
                    toolTip: qsTr("Browse for a media file")
                    onClicked: mediaDialog.open()
                }
            }

            TabBar {
                id: tabBar
                Layout.fillWidth: true

                background: Rectangle {
                    color: "#e4e6ea"
                    border.color: Theme.border
                }

                // Enable/disable by controller state: audio disables the Media
                // tab only, never Record (regression guard).
                TabButton {
                    text: qsTr("Media")
                    enabled: session.mediaTabEnabled
                    font.pixelSize: Theme.fontSizeSmall
                    background: Rectangle {
                        color: tabBar.currentItem === parent ? "#fafafa" : "#d7dade"
                        border.color: "#bbbbbb"
                    }
                }
                TabButton {
                    text: qsTr("Record")
                    font.pixelSize: Theme.fontSizeSmall
                    background: Rectangle {
                        color: tabBar.currentItem === parent ? "#fafafa" : "#d7dade"
                        border.color: "#bbbbbb"
                    }
                }
                TabButton {
                    text: qsTr("Batch")
                    font.pixelSize: Theme.fontSizeSmall
                    background: Rectangle {
                        color: tabBar.currentItem === parent ? "#fafafa" : "#d7dade"
                        border.color: "#bbbbbb"
                    }
                }
                TabButton {
                    text: qsTr("History")
                    font.pixelSize: Theme.fontSizeSmall
                    background: Rectangle {
                        color: tabBar.currentItem === parent ? "#fafafa" : "#d7dade"
                        border.color: "#bbbbbb"
                    }
                }
                onCurrentIndexChanged: {
                    const names = ["media", "record", "batch", "history"]
                    if (names[currentIndex] !== "media")
                        mediaPage.pausePlayback()
                    session.onTabChanged(currentIndex)
                }
            }

            StackLayout {
                id: tabPages
                Layout.fillWidth: true
                Layout.fillHeight: true
                // Widest hidden page must not dictate the column width.
                Layout.minimumWidth: 0
                currentIndex: tabBar.currentIndex
                clip: true

                MediaTab {
                    id: mediaPage
                    objectName: "mediaTabPage"
                }
                RecordTab {}
                BatchTab {}
                HistoryTab {}
            }
        }

        // RIGHT: scrollable settings + pinned action area
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.minimumHeight: 0
            spacing: 6

            ScrollView {
                id: settingsScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                // Let the scroll area shrink (and scroll) instead of forcing
                // the whole column past the window height.
                Layout.minimumHeight: 0
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                SettingsPanel {
                    width: settingsScroll.availableWidth
                    onBrowseOutputRequested: outputDialog.open()
                    onBrowseSupportRequested: supportDialog.open()
                }
            }

            PinnedActionArea {
                onSettingsRequested: window.settingsOpen = true
            }
        }
    }

    // Global keyboard shortcuts. Tab/arrow navigation is handled by the
    // controls themselves; these cover the primary actions.
    Shortcut {
        sequence: StandardKey.Open
        context: Qt.WindowShortcut
        onActivated: mediaDialog.open()
    }
    Shortcut {
        sequence: "Ctrl+,"
        context: Qt.WindowShortcut
        onActivated: window.settingsOpen = true
    }
    Shortcut {
        sequence: "Ctrl+Return"
        enabled: session.startEnabled
        context: Qt.WindowShortcut
        onActivated: session.startJob()
    }
    Shortcut {
        sequence: "Ctrl+."
        enabled: session.cancelEnabled
        context: Qt.WindowShortcut
        onActivated: session.cancelJob()
    }
    Shortcut {
        sequence: "Ctrl+1"
        context: Qt.WindowShortcut
        onActivated: tabBar.currentIndex = 0
    }
    Shortcut {
        sequence: "Ctrl+2"
        context: Qt.WindowShortcut
        onActivated: tabBar.currentIndex = 1
    }
    Shortcut {
        sequence: "Ctrl+3"
        context: Qt.WindowShortcut
        onActivated: tabBar.currentIndex = 2
    }
    Shortcut {
        sequence: "Ctrl+4"
        context: Qt.WindowShortcut
        onActivated: tabBar.currentIndex = 3
    }

    FileDialog {
        id: mediaDialog
        title: qsTr("Select media")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Media (*.mp4 *.mkv *.avi *.mov *.wav *.mp3 *.m4a)")]
        onAccepted: session.pendingInput = selectedFile
    }

    FolderDialog {
        id: outputDialog
        title: qsTr("Select output directory")
        onAccepted: jobForm.outputDir = selectedFolder
    }

    FileDialog {
        id: supportDialog
        title: qsTr("Add support files")
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            qsTr("Support files (*.vtt *.txt *.srt *.doc *.docx *.md *.png *.jpg *.jpeg)"),
            qsTr("All files (*.*)")
        ]
        onAccepted: jobForm.supportFilesToAdd = selectedFiles
    }

    Dialog {
        id: alertDialog
        modal: true
        standardButtons: Dialog.Ok
        anchors.centerIn: parent
        property string alertTitle: ""
        property string alertText: ""
        title: alertTitle

        contentItem: Text {
            text: alertDialog.alertText
            font.pixelSize: Theme.fontSizeSmall
            wrapMode: Text.Wrap
            width: 360
        }
    }

    Connections {
        target: session
        function onAlert(title, text) {
            alertDialog.alertTitle = title
            alertDialog.alertText = text
            alertDialog.open()
        }
        function onCloudConsentRequested(provider, model, summary) {
            cloudConsentDialog.detailText = summary + "\n\nProvider: " + provider
                    + (model.length > 0 ? "\nModel: " + model : "")
                    + "\n\nCloud API usage may incur charges. You can revoke consent in Settings."
            cloudConsentDialog.open()
        }
    }

    Dialog {
        id: cloudConsentDialog
        modal: true
        title: qsTr("Cloud AI consent required")
        anchors.centerIn: parent
        property string detailText: ""
        standardButtons: Dialog.NoButton

        contentItem: ColumnLayout {
            spacing: 12

            Text {
                text: cloudConsentDialog.detailText
                wrapMode: Text.Wrap
                width: 380
                font.pixelSize: Theme.fontSizeSmall
            }

            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 8

                Button {
                    text: qsTr("Cancel")
                    font.pixelSize: Theme.fontSizeSmall
                    onClicked: cloudConsentDialog.close()
                }
                Button {
                    text: qsTr("Continue with cloud AI")
                    font.pixelSize: Theme.fontSizeSmall
                    onClicked: {
                        cloudConsentDialog.close()
                        session.grantCloudConsentAndStart()
                    }
                }
            }
        }
    }

    Loader {
        active: window.settingsOpen
        sourceComponent: settingsDialogComponent
    }

    Component {
        id: settingsDialogComponent
        SettingsDialog {
            objectName: "settingsDialog"
            Component.onCompleted: open()
            onClosed: window.settingsOpen = false
        }
    }
}
