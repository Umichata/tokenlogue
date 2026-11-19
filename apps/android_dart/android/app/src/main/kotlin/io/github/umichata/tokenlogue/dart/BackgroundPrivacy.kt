package io.github.umichata.tokenlogue.dart

import android.app.Activity
import android.graphics.Color
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel

/**
 * Keep the previous Flutter surface covered across a real background transition.
 * Dart revokes its session and acknowledges only after rendering a locked frame.
 */
internal class BackgroundPrivacy(private val activity: Activity) {
    private var channel: MethodChannel? = null
    private var generation = 0L
    private var acknowledged = 0L
    private var resumed = false
    private var cover: View? = null
    private var addedSecureFlag = false
    private val previousAccessibility = mutableMapOf<View, Int>()

    fun attach(messenger: BinaryMessenger) {
        channel = MethodChannel(messenger, "io.github.umichata.tokenlogue.dart/lifecycle").apply {
            setMethodCallHandler { call, result ->
                if (call.method == "ready") {
                    result.success(null)
                    notifyDart()
                } else {
                    result.notImplemented()
                }
            }
        }
    }

    fun leave() {
        generation++
        if (cover == null) {
            val parent = activity.findViewById<ViewGroup>(android.R.id.content)
            for (i in 0 until parent.childCount) {
                val child = parent.getChildAt(i)
                previousAccessibility[child] = child.importantForAccessibility
                child.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            }
            val window = activity.window
            addedSecureFlag = window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE == 0
            if (addedSecureFlag) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
            cover = View(activity).apply {
                setBackgroundColor(Color.rgb(16, 25, 35))
                isClickable = true
                isFocusable = true
                parent.addView(this, ViewGroup.LayoutParams(-1, -1))
            }
        }
        notifyDart()
    }

    fun pause() { resumed = false }

    fun resume() {
        resumed = true
        if (acknowledged == generation) uncoverAfterFrame(generation) else notifyDart()
    }

    private fun notifyDart() {
        if (cover == null || acknowledged == generation) return
        val sent = generation
        channel?.invokeMethod("background", sent, object : MethodChannel.Result {
            override fun success(result: Any?) {
                if (sent != generation || (result as? Number)?.toLong() != sent) return
                acknowledged = sent
                uncoverAfterFrame(sent)
            }
            override fun error(errorCode: String, errorMessage: String?, details: Any?) {}
            override fun notImplemented() {}
        })
    }

    private fun uncoverAfterFrame(expected: Long) {
        val view = cover ?: return
        view.postOnAnimation {
            if (!resumed || generation != expected || acknowledged != expected || cover !== view) return@postOnAnimation
            (view.parent as? ViewGroup)?.removeView(view)
            cover = null
            previousAccessibility.forEach { (child, flag) -> child.importantForAccessibility = flag }
            previousAccessibility.clear()
            if (addedSecureFlag) activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        }
    }

    fun dispose() {
        channel?.setMethodCallHandler(null)
        channel = null
        previousAccessibility.clear()
    }
}
