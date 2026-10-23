#!/usr/bin/env python3
# Fullscreen looping video player for Weston (gtkwaylandsink inside a fullscreen GTK window).
import sys
import gi
gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gst, Gtk, Gdk

URI = "file:///root/BBeviL_Halloween_Teaser_2.mp4"

Gst.init(None)
player = Gst.ElementFactory.make("playbin", "player")
sink = Gst.ElementFactory.make("gtkwaylandsink", "sink")
player.set_property("uri", URI)
player.set_property("video-sink", sink)
player.set_property("volume", 1.0)

win = Gtk.Window(title="BBeviL Teaser")
win.connect("destroy", lambda *_: (player.set_state(Gst.State.NULL), Gtk.main_quit()))
win.add(sink.get_property("widget"))
win.fullscreen()
win.show_all()
win.get_window().set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))

def on_message(bus, msg):
    if msg.type == Gst.MessageType.EOS:
        player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
    elif msg.type == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg, file=sys.stderr, flush=True)
        Gtk.main_quit()

bus = player.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)
player.set_state(Gst.State.PLAYING)
Gtk.main()
