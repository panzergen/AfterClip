import QtQuick

Rectangle {
    id: root

    property real maximumMs: 0
    property real positionMs: 0
    property bool clipMode: false
    property real clipStartSec: 0
    property real clipEndSec: 0
    property var marks: []

    signal moved(real positionMs)
    signal clipRangeChanged(real startSec, real endSec)

    readonly property real padding: 10
    readonly property real secondsMax: maximumMs > 0 ? maximumMs / 1000 : 0

    function xFor(seconds) {
        if (secondsMax <= 0)
            return padding
        return padding + (width - 2 * padding) * Math.max(0, Math.min(seconds, secondsMax)) / secondsMax
    }

    function secondsFor(x) {
        if (secondsMax <= 0)
            return 0
        return Math.max(0, Math.min(secondsMax, (x - padding) * secondsMax / Math.max(1, width - 2 * padding)))
    }

    implicitWidth: 200
    implicitHeight: 28
    color: "transparent"

    Rectangle {  // rail
        y: parent.height / 2 - 2.5
        x: root.padding
        width: parent.width - 2 * root.padding
        height: 5
        radius: 2.5
        color: Theme.rail
    }

    Rectangle {  // clip range
        visible: root.clipMode && secondsMax > 0
        y: parent.height / 2 - 4.5
        x: root.xFor(root.clipStartSec)
        width: root.xFor(root.clipEndSec) - root.xFor(root.clipStartSec)
        height: 9
        radius: 4.5
        color: Theme.clip
    }

    Rectangle {  // clip start knob
        visible: root.clipMode && secondsMax > 0
        y: parent.height / 2 - 9
        x: root.xFor(root.clipStartSec) - 9
        width: 18
        height: 18
        radius: 9
        color: Theme.knob
    }

    Rectangle {  // clip end knob
        visible: root.clipMode && secondsMax > 0
        y: parent.height / 2 - 9
        x: root.xFor(root.clipEndSec) - 9
        width: 18
        height: 18
        radius: 9
        color: Theme.knob
    }

    Rectangle {  // play head
        y: 2
        x: root.xFor(root.positionMs / 1000) - 1
        width: 2
        height: parent.height - 4
        color: Theme.head
    }

    Repeater {  // bookmark markers
        model: root.marks

        delegate: Rectangle {
            required property var modelData
            visible: secondsMax > 0
            y: root.height / 2 - 13
            x: root.xFor(modelData) - 2
            width: 4
            height: 10
            radius: 1
            color: Theme.bookmark
            border.color: "#7a5b00"
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor

        property string handle: ""

        function nearestHandle(x) {
            const startDistance = Math.abs(x - root.xFor(root.clipStartSec))
            const endDistance = Math.abs(x - root.xFor(root.clipEndSec))
            return startDistance <= endDistance ? "start" : "end"
        }

        onPressed: (mouseEvent) => {
            if (root.clipMode && secondsMax > 0) {
                // Clip mode always drags the nearest handle so cropping is
                // reliable anywhere on the timeline.
                handle = nearestHandle(mouseEvent.x)
                moveClip(root.secondsFor(mouseEvent.x))
                return
            }
            handle = "position"
            movePosition(root.secondsFor(mouseEvent.x))
        }
        onPositionChanged: (mouseEvent) => {
            if (handle === "start" || handle === "end")
                moveClip(root.secondsFor(mouseEvent.x))
            else if (handle === "position")
                movePosition(root.secondsFor(mouseEvent.x))
        }
        onReleased: handle = ""

        function movePosition(seconds) {
            root.moved(seconds * 1000)
        }

        function moveClip(seconds) {
            let start = root.clipStartSec
            let end = root.clipEndSec
            if (handle === "start")
                start = Math.min(seconds, end)
            else
                end = Math.max(seconds, start)
            root.clipRangeChanged(start, end)
        }
    }

    WheelHandler {
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: (event) => {
            if (event.angleDelta.y === 0)
                return
            const step = secondsMax * 0.01 * (event.angleDelta.y > 0 ? 1 : -1)
            root.moved(Math.max(0, Math.min(root.positionMs / 1000 + step, secondsMax)) * 1000)
        }
    }

    Accessible.role: Accessible.Slider
    Accessible.name: qsTr("Playback timeline")
}
