import xml.etree.ElementTree as ET
import os
import subprocess
import shutil
import sys
import re

# === KONFIGURASI ===
MANIFEST_FILE = 'LA.UM.9.15.2.r1-08600-KAMORTA.QSSI12.0.xml'
CLO_BASE_URL = "https://git.codelinaro.org/clo/la/"
# Prefix agar repo Anda rapi. Contoh: "clo-kernel-msm-4.19"
REPO_PREFIX = "clo-backup-"

# Pastikan token ada
GH_PERSONAL_TOKEN = os.environ.get('GH_PERSONAL_TOKEN')
if not GH_PERSONAL_TOKEN:
    print("Error: Secret GH_PERSONAL_TOKEN belum diset di GitHub Actions!")
    sys.exit(1)

# Username GitHub pemilik token
try:
    GH_USERNAME = subprocess.check_output("gh api user -q .login", shell=True, text=True).strip()
except:
    print("Gagal mengambil username. Pastikan 'gh' terinstall dan terautentikasi.")
    sys.exit(1)

def run_cmd(cmd, cwd=None, capture_output=False, allow_failure=False):
    """Jalankan command dengan error handling yang lebih baik"""
    try:
        print(f"[RUN] {cmd[:100]}..." if len(cmd) > 100 else f"[RUN] {cmd}")
        if capture_output:
            result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
            if result.returncode != 0 and not allow_failure:
                print(f"[-] Error: {result.stderr}")
            return result
        else:
            result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[-] Error output: {result.stderr}")
                if not allow_failure:
                    return False
            return True
    except Exception as e:
        print(f"[-] Exception: {e}")
        if not allow_failure:
            return False
        return None if capture_output else False

def cleanup_path(path):
    """Bersihkan path dengan aman"""
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            print(f"[INFO] Cleared {path}")
        except Exception as e:
            print(f"[-] Gagal menghapus {path}: {e}")

def get_repo_tags(repo_path):
    """Dapatkan semua tag dari repository"""
    result = run_cmd("git tag -l", cwd=repo_path, capture_output=True, allow_failure=True)
    if result and result.returncode == 0:
        return result.stdout.strip().split('\n')
    return []

def sanitize_branch_name(name):
    """Sanitize branch name untuk menghindari karakter yang tidak valid"""
    # Hapus karakter berbahaya
    sanitized = re.sub(r'[^\w\-/.]', '_', name)
    # Hapus awalan/takhiran underscore
    sanitized = sanitized.strip('_')
    # Ganti multiple underscores dengan satu
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized

def process_project(name, revision, i, total, temp_dir):
    """Proses satu project"""
    print(f"\n[{i+1}/{total}] Processing: {name} (revision: {revision})")
    
    # Nama repo baru di GitHub (ganti / dengan _)
    new_repo_name = REPO_PREFIX + name.replace('/', '_')
    local_path = os.path.join(temp_dir, name.replace('/', '_'))

    # 1. CEK/BUAT REPO DI GITHUB
    print(f"    -> Mengecek repo di GitHub...")
    check = subprocess.run(
        f"gh repo view {GH_USERNAME}/{new_repo_name}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    if check.returncode != 0:
        print(f"    -> Membuat repo baru: {new_repo_name}")
        if not run_cmd(f"gh repo create {new_repo_name} --private --confirm"):
            print(f"[-] Gagal membuat repo {new_repo_name}")
            return False
    else:
        print(f"    -> Repo {new_repo_name} sudah ada.")

    # 2. CLONE DARI CLO
    print(f"    -> Cloning dari CLO...")
    clo_url = CLO_BASE_URL + name + ".git"
    
    # Hapus folder lama jika ada
    cleanup_path(local_path)
    
    # Clone dengan semua tag dan branch
    if not run_cmd(f"git clone --mirror {clo_url} {local_path}"):
        print(f"[-] Gagal mirror clone dari {clo_url}")
        cleanup_path(local_path)
        return False

    # 3. BUAT WORKING COPY DARI MIRROR
    print(f"    -> Membuat working copy...")
    working_path = local_path + "_work"
    cleanup_path(working_path)
    
    if not run_cmd(f"git clone {local_path} {working_path}"):
        print(f"[-] Gagal membuat working copy")
        cleanup_path(working_path)
        cleanup_path(local_path)
        return False

    # 4. CHECKOUT REVISI
    print(f"    -> Checkout revision: {revision}")
    
    # Cek apakah revision adalah tag
    tags = get_repo_tags(working_path)
    is_tag = revision in tags
    
    # Checkout ke revision
    if not run_cmd(f"git checkout {revision}", cwd=working_path):
        print(f"[-] Gagal checkout {revision}")
        cleanup_path(working_path)
        cleanup_path(local_path)
        return False

    # 5. BUAT BRANCH SESUAI TAG/REVISION
    if is_tag:
        # Jika revision adalah tag, buat branch dengan nama tag
        branch_name = sanitize_branch_name(f"tag_{revision}")
        print(f"    -> Revision adalah tag, membuat branch: {branch_name}")
        if not run_cmd(f"git checkout -b {branch_name}", cwd=working_path):
            print(f"    -> Gagal membuat branch {branch_name}, menggunakan main")
            branch_name = "main"
            run_cmd("git checkout -b main", cwd=working_path)
    else:
        # Jika revision adalah branch, gunakan nama branch tersebut
        branch_name = sanitize_branch_name(revision)
        print(f"    -> Revision adalah branch, menggunakan: {branch_name}")
        # Coba checkout ke branch tersebut
        run_cmd(f"git checkout -b {branch_name}", cwd=working_path, allow_failure=True)

    # 6. PUSH KE GITHUB DENGAN SEMUA TAG
    print(f"    -> Pushing ke GitHub...")
    
    # Hapus remote origin lama (CLO)
    run_cmd("git remote remove origin", cwd=working_path, allow_failure=True)
    
    # Tambah remote baru dengan Auth Token
    remote_url = f"https://{GH_USERNAME}:{GH_PERSONAL_TOKEN}@github.com/{GH_USERNAME}/{new_repo_name}.git"
    
    # Sembunyikan token dari log
    safe_remote_url = f"https://{GH_USERNAME}:[REDACTED]@github.com/{GH_USERNAME}/{new_repo_name}.git"
    print(f"    -> Menambahkan remote: {safe_remote_url}")
    
    if not run_cmd(f"git remote add origin {remote_url}", cwd=working_path):
        print(f"[-] Gagal menambahkan remote")
        cleanup_path(working_path)
        cleanup_path(local_path)
        return False
    
    # Push branch utama
    print(f"    -> Pushing branch {branch_name}...")
    if not run_cmd(f"git push -u origin {branch_name} --force", cwd=working_path):
        print(f"[-] Gagal push branch {branch_name}")
    
    # Push semua tag
    print(f"    -> Pushing semua tag...")
    if not run_cmd("git push origin --tags --force", cwd=working_path):
        print(f"[-] Gagal push tags")
    
    # 7. JIKA ADA TAG REVISION, BUAT RELEASE DI GITHUB
    if is_tag:
        print(f"    -> Membuat GitHub Release untuk tag {revision}...")
        # Buat release di GitHub
        release_cmd = f"gh release create {revision} --title '{revision}' --notes 'Automated sync from CLO' --repo {new_repo_name}"
        run_cmd(release_cmd, allow_failure=True)
    
    # 8. CLEANUP
    print(f"    -> Membersihkan folder lokal...")
    cleanup_path(working_path)
    cleanup_path(local_path)
    
    return True

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

    success_count = 0
    for i, proj in enumerate(projects):
        name = proj.get('name')
        path = proj.get('path', name)
        revision = proj.get('revision')
        
        if not name or not revision:
            print(f"[-] Skipping project: name atau revision tidak ditemukan")
            continue
        
        if process_project(name, revision, i, len(projects), temp_dir):
            success_count += 1

    # Cleanup folder temp utama
    cleanup_path(temp_dir)
    
    print(f"\n=== Sync Selesai ===")
    print(f"Berhasil: {success_count}/{len(projects)} repository")
    print(f"Gagal: {len(projects) - success_count} repository")
    
    if success_count < len(projects):
        sys.exit(1)

if __name__ == "__main__":
    main()
