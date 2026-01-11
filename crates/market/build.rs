use std::process::Command;

fn main() {
    // Determine which python to use
    let python_exe = if let Ok(exe) = std::env::var("PYTHON_SYS_EXECUTABLE") {
        exe
    } else if let Ok(output) = Command::new("which")
        .arg("python3")
        .output()
    {
        String::from_utf8_lossy(&output.stdout)
            .trim()
            .to_string()
    } else {
        "python3".to_string()
    };

    // Get Python configuration using sysconfig
    let config_output = Command::new(&python_exe)
        .arg("-c")
        .arg(
            "import sysconfig; \
            print(sysconfig.get_config_var('LIBDIR')); \
            print(sysconfig.get_config_var('LDLIBRARY') or ''); \
            print(sysconfig.get_config_var('FRAMEWORKDIR') or ''); \
            print(sysconfig.get_config_var('ABIFLAGS') or ''); \
            print(sysconfig.get_config_var('MULTIARCH') or ''); \
            print(sysconfig.get_config_var('PY_VERSION') or '')",
        )
        .output()
        .expect("Failed to get Python configuration");

    let output_str = String::from_utf8_lossy(&config_output.stdout);
    let mut lines = output_str.lines();

    let libdir = lines.next().unwrap_or("").trim();
    let ldlibrary = lines.next().unwrap_or("").trim();
    let frameworkdir = lines.next().unwrap_or("").trim();
    let abiflags = lines.next().unwrap_or("").trim();
    let multiarch = lines.next().unwrap_or("").trim();
    let py_version = lines.next().unwrap_or("").trim();

    // Try frameworkdir first (macOS)
    if !frameworkdir.is_empty() {
        println!("cargo:rustc-link-search=framework={}", frameworkdir);
        println!("cargo:rustc-link-lib=framework=Python");
    } else if !libdir.is_empty() {
        // Fallback to regular library path
        println!("cargo:rustc-link-search=native={}", libdir);

        // Construct the library name
        if !ldlibrary.is_empty() {
            // Use the LDLIBRARY directly if available
            let libname = ldlibrary
                .trim_start_matches("lib")
                .trim_end_matches(".a")
                .trim_end_matches(".so")
                .trim_end_matches(".dylib");
            println!("cargo:rustc-link-lib=dylib={}", libname);
        } else if !py_version.is_empty() {
            // Construct from version and abiflags
            let flags = if !abiflags.is_empty() {
                format!("python{}{}", py_version, abiflags)
            } else {
                format!("python{}", py_version)
            };
            println!("cargo:rustc-link-lib=dylib={}", flags);
        }
    }

    // Add multiarch path if available
    if !multiarch.is_empty() && !libdir.is_empty() {
        let multiarch_path = format!("{}/{}", libdir, multiarch);
        println!("cargo:rustc-link-search=native={}", multiarch_path);
    }
}
