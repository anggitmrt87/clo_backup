import xml.etree.ElementTree as ET
import os
import subprocess
import shutil
import sys

# === KONFIGURASI ===
MANIFEST_FILE = 'LA.UM.9.15.2.r1-08600-KAMORTA.QSSI12.0.xml'
CLO_BASE_URL = "https://git.codelinaro.org/clo/la/"
# Prefix agar repo Anda rapi. Contoh: "clo-kernel-msm-4.19"
REPO_PREFIX = "clo-backup-" 

# Pastikan token ada
GITHUB_TOKEN = os.environ.get('GH_TOKEN')
if not GITHUB_TOKEN:
    print("Error: Secret GH_PERSONAL_TOKEN belum diset di GitHub Actions!")
    sys.exit(1)

# Username GitHub pemilik token
try:
    GH_USERNAME = subprocess.check_output("gh api user -q .login", shell=True).decode().strip()
except:
    print("Gagal mengambil username. Pastikan 'gh' terinstall dan terautentikasi.")
    sys.exit(1)

def run_cmd(cmd, cwd=None):
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd)
        return True
    except subprocess.CalledProcessError:
        print(f"[-] Command gagal: {cmd}")
        return False

def main():
    if not os.path.exists(MANIFEST_FILE):
        print(f"File {MANIFEST_FILE} tidak ditemukan.")
        sys.exit(1)

    tree = ET.parse(MANIFEST_FILE)
    root = tree.getroot()
    projects = root.findall('project')
    
    print(f"=== Memulai Sync {len(projects)} Repository ===")
    
    # Buat folder temp
    temp_dir = "temp_work"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    for i, proj in enumerate(projects):
        name = proj.get('name')
        path = proj.get('path', name)
        revision = proj.get('revision')
        
        # Nama repo baru di GitHub (ganti / dengan _)
        new_repo_name = REPO_PREFIX + name.replace('/', '_')
        local_path = os.path.join(temp_dir, name.replace('/', '_')) # Flat folder biar aman

        print(f"\n[{i+1}/{len(projects)}] Processing: {name}")
        
        # 1. CEK/BUAT REPO DI GITHUB
        # Cek apakah repo sudah ada
        check = subprocess.run(f"gh repo view {new_repo_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if check.returncode != 0:
            print(f"    -> Membuat repo baru: {new_repo_name}")
            # Buat Private biar aman, ganti --public jika ingin publik
            if not run_cmd(f"gh repo create {new_repo_name} --private"): 
                continue
        else:
            print(f"    -> Repo {new_repo_name} sudah ada.")

        # 2. CLONE DARI CLO
        print(f"    -> Cloning dari CLO...")
        clo_url = CLO_BASE_URL + name
        if not run_cmd(f"git clone {clo_url} {local_path}"):
            # Bersihkan jika gagal
            if os.path.exists(local_path): shutil.rmtree(local_path)
            continue

        # 3. CHECKOUT REVISI
        print(f"    -> Checkout commit: {revision}")
        if not run_cmd(f"git checkout {revision}", cwd=local_path):
            shutil.rmtree(local_path)
            continue

        # 4. PUSH KE GITHUB
        print(f"    -> Pushing ke GitHub...")
        # Hapus remote origin lama (CLO)
        run_cmd("git remote remove origin", cwd=local_path)
        
        # Tambah remote baru dengan Auth Token embedded di URL
        remote_url = f"https://{GH_USERNAME}:{GITHUB_TOKEN}@github.com/{GH_USERNAME}/{new_repo_name}.git"
        run_cmd(f"git remote add origin {remote_url}", cwd=local_path)
        
        # Push force
        run_cmd("git push -u origin HEAD:main --force", cwd=local_path)

        # 5. CLEANUP (PENTING UNTUK HEMAT DISK SPACE)
        print(f"    -> Menghapus folder lokal untuk menghemat ruang...")
        shutil.rmtree(local_path)

if __name__ == "__main__":
    main()
