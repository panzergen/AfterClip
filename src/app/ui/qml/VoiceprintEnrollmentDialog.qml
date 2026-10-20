import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

Dialog {
    id: root

    title: qsTr("Name the detected speakers")
    modal: true
    standardButtons: Dialog.NoButton
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: 520
    height: Math.min(560, Overlay.overlay ? Overlay.overlay.height - 48 : 560)

    contentItem: ColumnLayout {
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: qsTr("The job found these distinct speakers. Play a segment to hear them, name one to enroll their voice globally (future jobs will recognize them), then reprocess the timeline.")
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                Layout.preferredWidth: 100
                text: qsTr("Merge similarity")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
            Slider {
                id: thresholdSlider
                Layout.fillWidth: true
                from: 0.30
                to: 0.70
                stepSize: 0.05
                value: voiceprintEnrollment.clusterThreshold
                onValueChanged: {
                    if (Math.abs(value - voiceprintEnrollment.clusterThreshold) > 0.0001)
                        voiceprintEnrollment.clusterThreshold = value
                }
            }
            Text {
                Layout.preferredWidth: 34
                text: thresholdSlider.value.toFixed(2)
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("Lower merges more segments into fewer speakers; higher keeps them separate.")
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.faint
            wrapMode: Text.Wrap
        }

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: scroll.availableWidth
                spacing: 6

                Text {
                    visible: voiceprintEnrollment.recognized.length > 0
                    Layout.fillWidth: true
                    text: qsTr("Recognized by voice:")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }

                Repeater {
                    model: voiceprintEnrollment.recognized
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            font.pixelSize: Theme.fontSizeSmall
                            color: Theme.ok
                        }
                        Text {
                            text: qsTr("(%1 seg)").arg(modelData.segments)
                            font.pixelSize: Theme.fontSizeCaption
                            color: Theme.faint
                        }
                    }
                }

                Text {
                    visible: voiceprintEnrollment.speakers.length > 0
                    Layout.fillWidth: true
                    text: qsTr("Not recognized (name these):")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }

                Repeater {
                    model: voiceprintEnrollment.speakers
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            Layout.minimumWidth: 100
                            text: modelData.label
                            font.pixelSize: Theme.fontSizeSmall
                            color: Theme.muted
                            elide: Text.ElideRight
                        }

                        Text {
                            text: qsTr("(%1 seg)").arg(modelData.segments)
                            font.pixelSize: Theme.fontSizeCaption
                            color: Theme.faint
                        }

                        IconButton {
                            glyph: "\u25B6"
                            toolTip: qsTr("Play a sample segment")
                            onClicked: voiceprintEnrollment.playSegment(index)
                        }
                        IconButton {
                            glyph: "\u25A0"
                            toolTip: qsTr("Stop")
                            onClicked: voiceprintEnrollment.stopSegment()
                        }

                        TextField {
                            Layout.fillWidth: true
                            placeholderText: qsTr("Name")
                            text: modelData.name
                            font.pixelSize: Theme.fontSizeSmall
                            selectByMouse: true
                            onTextEdited: voiceprintEnrollment.setName(index, text)
                        }

                        Button {
                            text: qsTr("Enroll")
                            font.pixelSize: Theme.fontSizeSmall
                            onClicked: voiceprintEnrollment.enroll(index)
                        }
                    }
                }
            }
        }

        Text {
            visible: voiceprintEnrollment.statusText.length > 0
            Layout.fillWidth: true
            text: voiceprintEnrollment.statusText
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8

            Button {
                text: qsTr("Close")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: voiceprintEnrollment.close()
            }
            Button {
                text: qsTr("Save names & reprocess")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: voiceprintEnrollment.reprocess()
            }
        }
    }
}
