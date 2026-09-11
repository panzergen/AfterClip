import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

GroupBox {
    id: root

    signal browseOutputRequested()
    signal browseSupportRequested()

    title: qsTr("Job settings")
    font.pixelSize: Theme.fontSizeSmall

    background: Rectangle {
        color: Theme.panel
        border.color: Theme.border
        radius: 4
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Output directory")

            RowLayout {
                width: parent.width
                spacing: 8
                TextField {
                    id: outputField
                    Layout.fillWidth: true
                    height: Theme.controlHeight
                    text: jobForm.outputDir
                    font.pixelSize: Theme.fontSizeSmall
                    selectByMouse: true
                    onEditingFinished: jobForm.outputDir = text
                    background: Rectangle {
                        color: Theme.field
                        border.color: outputField.activeFocus ? Theme.primary : Theme.fieldBorder
                        radius: 3
                    }
                }
                IconButton {
                    glyph: "\uD83D\uDCC2"
                    toolTip: qsTr("Browse for a folder")
                    onClicked: root.browseOutputRequested()
                }
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Language")
            TextField {
                width: Math.min(240, parent.width)
                height: Theme.controlHeight
                placeholderText: qsTr("Optional, e.g. tr")
                text: jobForm.language
                font.pixelSize: Theme.fontSizeSmall
                selectByMouse: true
                onEditingFinished: jobForm.language = text
                background: Rectangle {
                    color: Theme.field
                    border.color: parent.activeFocus ? Theme.primary : Theme.fieldBorder
                    radius: 3
                }
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Target task")
            TextField {
                width: parent.width
                height: Theme.controlHeight
                placeholderText: qsTr("E.g., Summarize the meeting decisions...")
                text: jobForm.task
                font.pixelSize: Theme.fontSizeSmall
                selectByMouse: true
                onEditingFinished: jobForm.task = text
                background: Rectangle {
                    color: Theme.field
                    border.color: parent.activeFocus ? Theme.primary : Theme.fieldBorder
                    radius: 3
                }
            }
        }

        CheckBox {
            Layout.fillWidth: true
            text: qsTr("Reuse existing transcription (skip Whisper)")
            checked: jobForm.reuseTranscription
            onToggled: jobForm.reuseTranscription = checked
            font.pixelSize: Theme.fontSizeSmall
            ToolTip.visible: hovered
            ToolTip.delay: 400
            ToolTip.text: qsTr("Reuses the transcript already produced for the selected input file in the output directory, then regenerates the timeline and reports. Whisper is not run again.")
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Support files")

            ColumnLayout {
                width: parent.width
                spacing: 4

                ListView {
                    id: supportList
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(64, count * 24 + 4)
                    clip: true
                    model: jobForm.supportFiles

                    delegate: Rectangle {
                        id: supportRow
                        required property int index
                        required property var modelData
                        width: supportList.width
                        height: 22
                        color: supportList.currentIndex === index ? "#dce9f8" : Theme.field

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 6
                            anchors.rightMargin: 6
                            Text {
                                Layout.fillWidth: true
                                text: supportRow.modelData.name
                                font.pixelSize: Theme.fontSizeCaption
                                elide: Text.ElideRight
                            }
                            Text {
                                text: supportRow.modelData.note
                                font.pixelSize: Theme.fontSizeCaption
                                color: Theme.muted
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: supportList.currentIndex = supportRow.index
                        }
                    }
                }

                Row {
                    spacing: 8
                    Button {
                        text: qsTr("Add files...")
                        font.pixelSize: Theme.fontSizeSmall
                        onClicked: root.browseSupportRequested()
                    }
                    Button {
                        text: qsTr("Remove selected")
                        font.pixelSize: Theme.fontSizeSmall
                        onClicked: jobForm.removeSupportFile(supportList.currentIndex)
                    }
                }

                Text {
                    text: qsTr("VTT files drive speaker diarization; other types are stored for later use.")
                    font.pixelSize: Theme.fontSizeCaption
                    color: Theme.muted
                }
            }
        }
    }
}
