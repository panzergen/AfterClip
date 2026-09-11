import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import "components"

ColumnLayout {
    id: root

    property var selectedRows: []

    spacing: 8

    Text {
        Layout.fillWidth: true
        text: qsTr("Add media files; they run one by one with the settings captured when added.")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
        wrapMode: Text.Wrap
    }

    ListView {
        id: jobsList
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: batch.model
        spacing: 0

        delegate: Rectangle {
            id: rowDelegate
            required property int index
            required property string name
            required property string status
            required property string error

            width: jobsList.width
            height: 30
            color: root.selectedRows.includes(index) ? "#dce9f8" : "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: rowDelegate.name
                    font.pixelSize: Theme.fontSizeSmall
                    elide: Text.ElideRight
                }

                Text {
                    visible: rowDelegate.error.length > 0
                    text: rowDelegate.error
                    font.pixelSize: Theme.fontSizeCaption
                    color: Theme.danger
                    elide: Text.ElideMiddle
                    Layout.maximumWidth: jobsList.width / 2
                }

                StatusPill {
                    status: rowDelegate.status
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    const position = root.selectedRows.indexOf(rowDelegate.index)
                    if (position >= 0)
                        root.selectedRows.splice(position, 1)
                    else
                        root.selectedRows.push(rowDelegate.index)
                    root.selectedRowsChanged()
                }
            }
        }

        Text {
            anchors.centerIn: parent
            visible: jobsList.count === 0
            text: qsTr("No jobs queued")
            color: Theme.faint
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Flow {
        Layout.fillWidth: true
        spacing: 8

        Button {
            text: qsTr("Add files...")
            font.pixelSize: Theme.fontSizeSmall
            onClicked: addDialog.open()
        }
        Button {
            text: qsTr("Remove selected")
            enabled: batch.removeEnabled && root.selectedRows.length > 0
            font.pixelSize: Theme.fontSizeSmall
            onClicked: {
                batch.rowsToRemove = root.selectedRows
                root.selectedRows = []
            }
        }
        Button {
            text: qsTr("Start batch")
            enabled: batch.startEnabled
            font.pixelSize: Theme.fontSizeSmall
            onClicked: batch.startBatch()
        }
        Button {
            text: qsTr("Cancel batch")
            enabled: batch.cancelEnabled
            font.pixelSize: Theme.fontSizeSmall
            onClicked: batch.cancelBatch()
        }
        Button {
            text: qsTr("Retry failed")
            font.pixelSize: Theme.fontSizeSmall
            onClicked: batch.retryFailed()
        }
        Button {
            text: qsTr("Refresh")
            font.pixelSize: Theme.fontSizeSmall
            onClicked: batch.refresh()
        }
    }

    Text {
        text: batch.statusText
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }

    FileDialog {
        id: addDialog
        title: qsTr("Add media to batch")
        fileMode: FileDialog.OpenFiles
        nameFilters: [qsTr("Media (*.mp4 *.mkv *.avi *.mov *.wav *.mp3 *.m4a)")]
        onAccepted: batch.filesToAdd = selectedFiles
    }
}
