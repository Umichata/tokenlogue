import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}

val signingFile = providers.environmentVariable("TOKENLOGUE_DART_SIGNING_PROPERTIES")
val signingValues = Properties().apply {
    if (signingFile.isPresent) file(signingFile.get()).inputStream().use { load(it) }
}

android {
    namespace = "io.github.umichata.tokenlogue.dart"
    compileSdk = 36
    ndkVersion = "28.2.13676358"
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    defaultConfig {
        applicationId = "io.github.umichata.tokenlogue.dart"
        minSdk = 24
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }
    signingConfigs {
        create("dartRelease") {
            if (signingFile.isPresent) {
                storeFile = file(signingValues.getProperty("storeFile"))
                storePassword = signingValues.getProperty("storePassword")
                keyAlias = signingValues.getProperty("keyAlias")
                keyPassword = signingValues.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        release { signingConfig = signingConfigs.getByName("dartRelease") }
    }
}

kotlin { compilerOptions { jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17 } }
flutter { source = "../.." }
