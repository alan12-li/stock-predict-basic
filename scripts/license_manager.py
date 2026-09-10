"""股票初级预测 — 授权管理
未授权用户只能运行 fetch_snapshots.py（数据抓取），
predict_batch.py / predict_single.py / settle.py 需要有效授权。
"""
import hashlib, json, os, pathlib, sys, uuid

LICENSE_FILE = pathlib.Path.home() / ".stock_predict_license"
SALT = "stock-predict-basic-v1"  # 公开盐值，不是秘密

def get_machine_fingerprint() -> str:
    """生成机器指纹（hostname + username + mac 地址哈希）"""
    import socket, getpass
    raw = f"{socket.gethostname()}:{getpass.getuser()}:{uuid.getnode()}:{SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def generate_license_code(machine_fingerprint: str, secret_key: str) -> str:
    """生成授权码（管理员用）—— 需要 secret_key，不公开"""
    raw = f"{machine_fingerprint}:{secret_key}:{SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def check_license() -> tuple[bool, str]:
    """检查当前机器是否有有效授权"""
    if not LICENSE_FILE.exists():
        return False, f"未找到授权文件 {LICENSE_FILE}\n请向项目作者申请授权码"
    
    try:
        data = json.loads(LICENSE_FILE.read_text())
        stored_code = data.get("license_code")
        stored_fp = data.get("machine_fingerprint")
        
        # 验证机器指纹
        current_fp = get_machine_fingerprint()
        if stored_fp != current_fp:
            return False, "授权码与当前机器不匹配（授权码绑定机器，不可复制）"
        
        # 验证授权码格式（不验证内容，内容验证需要 secret_key）
        if not stored_code or len(stored_code) != 24:
            return False, "授权码格式无效"
        
        return True, f"授权有效 (机器指纹: {current_fp[:8]}...)"
    
    except Exception as e:
        return False, f"授权文件损坏: {e}"

def require_license(func_name: str = "此功能"):
    """装饰器：检查授权，未授权则退出"""
    ok, msg = check_license()
    if not ok:
        print(f"❌ {func_name}需要授权")
        print(f"   {msg}")
        print(f"\n   机器指纹: {get_machine_fingerprint()}")
        print(f"   请将此指纹发送给项目作者获取授权码")
        print(f"   授权文件路径: {LICENSE_FILE}")
        sys.exit(1)
    print(f"✅ {msg}")

# 管理员功能：生成授权码（需要 secret_key，不公开）
def admin_generate_license():
    """管理员生成授权码 — 需要输入 secret_key"""
    print("=== 管理员模式：生成授权码 ===")
    fp = input("请输入用户机器指纹: ").strip()
    secret = input("请输入管理员密钥: ").strip()
    if not secret:
        print("需要管理员密钥")
        return
    code = generate_license_code(fp, secret)
    print(f"\n授权码: {code}")
    print(f"机器指纹: {fp}")
    print(f"\n用户保存到: {LICENSE_FILE}")
    print(json.dumps({"license_code": code, "machine_fingerprint": fp}, indent=2))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--admin":
        admin_generate_license()
    else:
        ok, msg = check_license()
        print(msg)
        sys.exit(0 if ok else 1)
