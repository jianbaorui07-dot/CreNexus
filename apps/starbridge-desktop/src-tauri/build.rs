fn main() {
    println!("cargo:rerun-if-env-changed=STARBRIDGE_LICENSE_PUBLIC_KEY_B64");
    println!("cargo:rerun-if-env-changed=STARBRIDGE_LICENSE_KEY_ID");
    tauri_build::build()
}
