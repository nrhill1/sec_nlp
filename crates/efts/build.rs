use std::env;
use std::process::Command;

fn candidate_python() -> String {
    if let Ok(exe) = env::var("PYTHON_SYS_EXECUTABLE").or_else(|_| env::var("PYO3_PYTHON")) {
        if !exe.trim().is_empty() {
            return exe;
        }
    }

    for candidate in ["python3.13", "python3"] {
        if let Ok(output) = Command::new("which").arg(candidate).output() {
            if output.status.success() {
                let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !value.is_empty() {
                    return value;
                }
            }
        }
    }

    "python3".to_string()
}

fn main() {
    println!("cargo:rerun-if-env-changed=PYTHON_SYS_EXECUTABLE");
    println!("cargo:rerun-if-env-changed=PYO3_PYTHON");

    pyo3_build_config::use_pyo3_cfgs();
    pyo3_build_config::add_extension_module_link_args();

    let python = candidate_python();

    let output = Command::new(&python)
        .arg("-c")
        .arg(
            "import sysconfig; \
print(sysconfig.get_config_var('LIBDIR') or ''); \
print(sysconfig.get_config_var('LDLIBRARY') or ''); \
print(sysconfig.get_config_var('PYTHONFRAMEWORK') or ''); \
print(sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX') or ''); \
print(sysconfig.get_config_var('LDVERSION') or ''); \
print(sysconfig.get_config_var('MULTIARCH') or '')",
        )
        .output();

    let Ok(output) = output else {
        return;
    };
    if !output.status.success() {
        return;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut lines = stdout.lines();

    let libdir = lines.next().unwrap_or("").trim();
    let ldlibrary = lines.next().unwrap_or("").trim();
    let framework = lines.next().unwrap_or("").trim();
    let framework_prefix = lines.next().unwrap_or("").trim();
    let ldversion = lines.next().unwrap_or("").trim();
    let multiarch = lines.next().unwrap_or("").trim();

    if !framework.is_empty() && !framework_prefix.is_empty() {
        println!("cargo:rustc-link-search=framework={framework_prefix}");
        println!("cargo:rustc-link-lib=framework={framework}");
        println!("cargo:rustc-link-arg=-Wl,-rpath,{framework_prefix}");
        return;
    }

    if !libdir.is_empty() {
        println!("cargo:rustc-link-search=native={libdir}");

        if !multiarch.is_empty() {
            println!("cargo:rustc-link-search=native={libdir}/{multiarch}");
        }
    }

    let mut libname = ldlibrary
        .rsplit('/')
        .next()
        .unwrap_or(ldlibrary)
        .trim_start_matches("lib")
        .trim_end_matches(".a")
        .trim_end_matches(".so")
        .trim_end_matches(".dylib")
        .to_string();

    if libname.is_empty() && !ldversion.is_empty() {
        libname = format!("python{ldversion}");
    }

    if !libname.is_empty() {
        println!("cargo:rustc-link-lib=dylib={libname}");
    }
}
