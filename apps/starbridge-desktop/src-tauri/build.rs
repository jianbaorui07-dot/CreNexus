fn main() {
    println!("cargo:rerun-if-env-changed=STARBRIDGE_LICENSE_PUBLIC_KEY_B64");
    println!("cargo:rerun-if-env-changed=STARBRIDGE_LICENSE_KEY_ID");
    println!("cargo:rerun-if-env-changed=STARBRIDGE_UPDATE_PUBLIC_KEY");
    tauri_build::build()
}
