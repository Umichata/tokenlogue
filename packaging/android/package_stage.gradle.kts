// Подготовка подтверждённого staging обязательна до упаковки Python ZIP.
val tokenloguePackagingAbi = "__TOKENLOGUE_ANDROID_ABI__"
val tokenloguePreparePackageStage = tasks.register<Exec>("tokenloguePreparePackageStage") {
    outputs.upToDateWhen { false }
    doFirst {
        val source = rootProject.projectDir.resolve("../../..").canonicalFile
        val python = System.getenv("TOKENLOGUE_PACKAGING_PYTHON")
            ?.takeIf { it.isNotBlank() }
            ?: throw GradleException("Tokenlogue packaging interpreter is not configured")
        commandLine(
            python,
            "-I",
            "-B",
            source.resolve("packaging/android/package_stage.py").path,
            "--run-dir",
            source.parentFile.path,
            "--abi",
            tokenloguePackagingAbi,
        )
    }
}

subprojects {
    if (path == ":serious_python_android") {
        tasks.configureEach {
            if (
                name.startsWith("splitSitePackages_") ||
                name.startsWith("splitStdlib_") ||
                name == "packageApp"
            ) {
                dependsOn(tokenloguePreparePackageStage)
            }
        }
    }
}

gradle.projectsEvaluated {
    val pythonProject = rootProject.findProject(":serious_python_android")
        ?: throw GradleException("Tokenlogue Python packaging project is missing")
    val zipTasks = pythonProject.tasks.names
    if (
        "splitSitePackages_$tokenloguePackagingAbi" !in zipTasks ||
        "splitStdlib_$tokenloguePackagingAbi" !in zipTasks ||
        "packageApp" !in zipTasks
    ) {
        throw GradleException("Tokenlogue Python ZIP packaging tasks are missing")
    }
}
