import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.zip.ZipFile
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

class MainActivity : FlutterFragmentActivity() {
    private val storageSyncIo = Executors.newSingleThreadExecutor()
    private val storageSyncReply = Handler(Looper.getMainLooper())
    private val nativeAlive = AtomicBoolean(true)
    private val commitSession = UUID.randomUUID().toString()
    private val commitSequence = AtomicLong(0)

    override fun onDestroy() {
        nativeAlive.set(false)
        storageSyncIo.shutdown()
        super.onDestroy()
    }

    private fun syncSecureStorage(result: MethodChannel.Result) {
        if (!nativeAlive.get()) {
            result.success(false)
            return
        }
        try {
            storageSyncIo.execute {
                var success = true
                // Перечень закрыт и относится только к хранилищам текущего приложения.
                val names = listOf(
                    "FlutterSecureKeyStorage",
                    "FlutterSecureStorageConfiguration:io.github.umichata.tokenlogue.secure_credentials",
                    "io.github.umichata.tokenlogue.secure_credentials"
                )
                for (name in names) {
                    val written = try {
                        // Счётчик растёт в уникальной сессии без чтения сохранённых значений.
                        val marker = "$commitSession:${commitSequence.incrementAndGet()}"
                        applicationContext.getSharedPreferences(name, MODE_PRIVATE)
                            .edit()
                            .putString("__tokenlogue_native_sync__", marker)
                            .commit()
                    } catch (_: Exception) {
                        false
                    }
                    success = written && success
                }
                storageSyncReply.post {
                    result.success(success && nativeAlive.get())
                }
            }
        } catch (_: Exception) {
            result.success(false)
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "io.github.umichata.tokenlogue.native_paths"
        ).setMethodCallHandler { call, result ->
            if (call.method == "syncSecureStorage") {
                syncSecureStorage(result)
                return@setMethodCallHandler
            }
            if (call.method == "platformCapabilities") {
                result.success(mapOf(
                    "api_level" to Build.VERSION.SDK_INT,
                    "recovery_supported" to (Build.VERSION.SDK_INT >= 30)
                ))
                return@setMethodCallHandler
            }
            if (call.method != "nativeEnvironment") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            try {
                result.success(nativeEnvironment())
            } catch (_: Exception) {
                result.error("native_paths_unavailable", null, null)
            }
        }
    }

    private fun nativeEnvironment(): Map<String, String> {
        // ABI закрепляет рецепт единственного APK, а не порядок ABI устройства.
        val abi = "__TOKENLOGUE_ANDROID_ABI__"
        val candidates = listOf(applicationInfo.sourceDir) +
            (applicationInfo.splitSourceDirs?.toList() ?: emptyList())
        val marker = "lib/$abi/libdart_bridge.so"
        val apk = candidates.firstOrNull { candidate ->
            ZipFile(candidate).use { archive -> archive.getEntry(marker) != null }
        } ?: throw IllegalStateException("native_abi_missing")
        return mapOf(
            "ANDROID_NATIVE_LIBRARY_DIR" to applicationInfo.nativeLibraryDir,
            "ANDROID_APK_NATIVE_PREFIX" to "$apk!/lib/$abi/"
        )
    }
}
