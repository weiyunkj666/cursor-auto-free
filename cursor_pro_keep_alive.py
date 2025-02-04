import os
import platform
import json
import sys
from colorama import Fore, Style

from exit_cursor import ExitCursor
import patch_cursor_get_machine_id
from reset_machine import MachineIDResetter

os.environ["PYTHONVERBOSE"] = "0"
os.environ["PYINSTALLER_VERBOSE"] = "0"

import time
import random
from cursor_auth_manager import CursorAuthManager
import os
from logger import logging
from browser_utils import BrowserManager
from get_email_code import EmailVerificationHandler
from logo import print_logo
from config import Config
from datetime import datetime

# 定义 EMOJI 字典
EMOJI = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}


def save_screenshot(tab, prefix="turnstile"):
    """保存截图
    Args:
        tab: 浏览器标签页对象
        prefix: 文件名前缀
    Returns:
        str: 截图文件路径
    """
    try:
        # 创建 screenshots 目录
        screenshot_dir = "screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)

        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        # 使用 get_screenshot 方法保存截图
        tab.get_screenshot(filepath)
        logging.info(f"已保存截图: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"截图保存失败: {str(e)}")
        return None


def handle_turnstile(tab, max_wait_time=60, retry_attempts=3):
    """
    处理 Turnstile 人机验证

    Args:
        tab: 浏览器标签页对象
        max_wait_time: 最大等待时间（秒）
        retry_attempts: 验证失败后的重试次数

    Returns:
        bool: 验证是否成功
    """
    logging.info("正在检测 Turnstile 验证...")
    start_time = time.time()

    success_selectors = {
        "password": "@name=password",
        "verification": "@data-index=0",
        "settings": "Account Settings",
    }

    while time.time() - start_time < max_wait_time:
        try:
            # 检查是否已经通过验证
            for name, selector in success_selectors.items():
                if tab.ele(selector, timeout=1):
                    logging.info(f"验证成功 - 已到达{name}页面")
                    break

            # 检查并处理 Turnstile 验证
            turnstile = tab.ele("@id=cf-turnstile", timeout=1)
            if turnstile:
                for attempt in range(retry_attempts):
                    try:
                        challengeCheck = (
                            turnstile.child()
                            .shadow_root.ele("tag:iframe")
                            .ele("tag:body")
                            .sr("tag:input")
                        )

                        if challengeCheck:
                            logging.info(
                                f"检测到 Turnstile 验证，正在处理... (尝试 {attempt + 1}/{retry_attempts})"
                            )
                            time.sleep(random.uniform(1, 2))
                            challengeCheck.click()
                            time.sleep(2)

                            # 保存验证过程的截图
                            save_screenshot(tab, f"turnstile_attempt_{attempt + 1}")

                            # 检查验证失败提示
                            error_text = (
                                "Can't verify the user is human. Please try again."
                            )

                            # 检查验证失败的标志，使用更精确的选择器
                            error_selectors = [
                                "@data-accent-color=red",  # 红色提示div
                                f"//div[contains(@class, 'rt-Text') and contains(text(), '{error_text}')]",  # 包含特定类和文本的div
                                f"//div[@data-accent-color='red' and contains(text(), '{error_text}')]",  # 最精确的选择器
                            ]

                            is_failed = any(
                                tab.ele(selector, timeout=2)
                                for selector in error_selectors
                            )

                            if not is_failed:
                                logging.info("人机验证成功")
                                save_screenshot(tab, "turnstile_success")
                                return True

                            logging.warning(
                                f"验证失败，尝试重试 ({attempt + 1}/{retry_attempts})"
                            )
                            # 保存失败的截图
                            save_screenshot(tab, f"turnstile_fail_{attempt + 1}")

                    except Exception as e:
                        logging.debug(f"处理验证时发生异常: {str(e)}")
                        continue

            time.sleep(1)

        except Exception as e:
            logging.debug(f"验证过程发生异常: {str(e)}")
            time.sleep(1)

    logging.error(f"Turnstile 验证超时，已等待 {max_wait_time} 秒")
    return False


def get_cursor_session_token(tab, max_attempts=3, retry_interval=2):
    """
    获取Cursor会话token，带有重试机制
    :param tab: 浏览器标签页
    :param max_attempts: 最大尝试次数
    :param retry_interval: 重试间隔(秒)
    :return: session token 或 None
    """
    logging.info("开始获取cookie")
    attempts = 0

    while attempts < max_attempts:
        try:
            cookies = tab.cookies()
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    return cookie["value"].split("%3A%3A")[1]

            attempts += 1
            if attempts < max_attempts:
                logging.warning(
                    f"第 {attempts} 次尝试未获取到CursorSessionToken，{retry_interval}秒后重试..."
                )
                time.sleep(retry_interval)
            else:
                logging.error(
                    f"已达到最大尝试次数({max_attempts})，获取CursorSessionToken失败"
                )

        except Exception as e:
            logging.error(f"获取cookie失败: {str(e)}")
            attempts += 1
            if attempts < max_attempts:
                logging.info(f"将在 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)

    return None


def update_cursor_auth(email=None, access_token=None, refresh_token=None):
    """
    更新Cursor的认证信息的便捷函数
    """
    auth_manager = CursorAuthManager()
    return auth_manager.update_auth(email, access_token, refresh_token)


def sign_up_account(browser, tab):
    logging.info("=== 开始注册账号流程 ===")
    logging.info(f"正在访问注册页面: {sign_up_url}")
    tab.get(sign_up_url)

    try:
        if tab.ele("@name=first_name"):
            logging.info("正在填写个人信息...")
            tab.actions.click("@name=first_name").input(first_name)
            logging.info(f"已输入名字: {first_name}")
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=last_name").input(last_name)
            logging.info(f"已输入姓氏: {last_name}")
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=email").input(account)
            logging.info(f"已输入邮箱: {account}")
            time.sleep(random.uniform(1, 3))

            logging.info("提交个人信息...")
            tab.actions.click("@type=submit")

    except Exception as e:
        logging.error(f"注册页面访问失败: {str(e)}")
        return False

    handle_turnstile(tab)

    try:
        if tab.ele("@name=password"):
            logging.info("正在设置密码...")
            tab.ele("@name=password").input(password)
            time.sleep(random.uniform(1, 3))

            logging.info("提交密码...")
            tab.ele("@type=submit").click()
            logging.info("密码设置完成，等待系统响应...")

    except Exception as e:
        logging.error(f"密码设置失败: {str(e)}")
        return False

    if tab.ele("This email is not available."):
        logging.error("注册失败：邮箱已被使用")
        return False

    handle_turnstile(tab)

    while True:
        try:
            if tab.ele("Account Settings"):
                logging.info("注册成功 - 已进入账户设置页面")
                break
            if tab.ele("@data-index=0"):
                logging.info("正在获取邮箱验证码...")
                code = email_handler.get_verification_code()
                if not code:
                    logging.error("获取验证码失败")
                    return False

                logging.info(f"成功获取验证码: {code}")
                logging.info("正在输入验证码...")
                i = 0
                for digit in code:
                    tab.ele(f"@data-index={i}").input(digit)
                    time.sleep(random.uniform(0.1, 0.3))
                    i += 1
                logging.info("验证码输入完成")
                break
        except Exception as e:
            logging.error(f"验证码处理过程出错: {str(e)}")

    handle_turnstile(tab)
    wait_time = random.randint(3, 6)
    for i in range(wait_time):
        logging.info(f"等待系统处理中... 剩余 {wait_time-i} 秒")
        time.sleep(1)

    logging.info("正在获取账户信息...")
    tab.get(settings_url)
    try:
        usage_selector = (
            "css:div.col-span-2 > div > div > div > div > "
            "div:nth-child(1) > div.flex.items-center.justify-between.gap-2 > "
            "span.font-mono.text-sm\\/\\[0\\.875rem\\]"
        )
        usage_ele = tab.ele(usage_selector)
        if usage_ele:
            usage_info = usage_ele.text
            total_usage = usage_info.split("/")[-1].strip()
            logging.info(f"账户可用额度上限: {total_usage}")
    except Exception as e:
        logging.error(f"获取账户额度信息失败: {str(e)}")

    logging.info("\n=== 注册完成 ===")
    account_info = f"Cursor 账号信息:\n邮箱: {account}\n密码: {password}"
    logging.info(account_info)
    time.sleep(5)
    return True


class EmailGenerator:
    def __init__(
        self,
        password="".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*",
                k=12,
            )
        ),
    ):
        configInstance = Config()
        configInstance.print_config()
        self.domain = configInstance.get_domain()
        self.default_password = password
        self.default_first_name = self.generate_random_name()
        self.default_last_name = self.generate_random_name()

    def generate_random_name(self, length=6):
        """生成随机用户名"""
        first_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        rest_letters = "".join(
            random.choices("abcdefghijklmnopqrstuvwxyz", k=length - 1)
        )
        return first_letter + rest_letters

    def generate_email(self, length=8):
        """生成随机邮箱地址"""
        random_str = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=length))
        timestamp = str(int(time.time()))[-6:]  # 使用时间戳后6位
        return f"{random_str}{timestamp}@{self.domain}"

    def get_account_info(self):
        """获取完整的账号信息"""
        return {
            "email": self.generate_email(),
            "password": self.default_password,
            "first_name": self.default_first_name,
            "last_name": self.default_last_name,
        }


def get_user_agent():
    """获取user_agent"""
    try:
        # 使用JavaScript获取user agent
        browser_manager = BrowserManager()
        browser = browser_manager.init_browser()
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")
        browser_manager.quit()
        return user_agent
    except Exception as e:
        logging.error(f"获取user agent失败: {str(e)}")
        return None


def check_cursor_version():
    """检查cursor版本"""
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            package_path = (
                "/Applications/Cursor.app/Contents/Resources/app/package.json"
            )
        elif system == "Windows":  # Windows
            program_files = os.environ.get("ProgramFiles")
            package_path = os.path.join(
                program_files, "Cursor", "resources", "app", "package.json"
            )
        else:
            logging.error(f"不支持的操作系统: {system}")
            return None

        if not os.path.exists(package_path):
            logging.warning(
                "未找到 Cursor 安装, 或者你自定义了安装路径；默认版本小于0.45"
            )
            return None

        with open(package_path, "r", encoding="utf-8") as f:
            package_data = json.load(f)
            version = package_data.get("version")
            if version:
                logging.info(f"Cursor 版本: {version}")
                version_parts = version.split(".")
                if len(version_parts) >= 2:
                    major_minor = float(f"{version_parts[0]}.{version_parts[1]}")
                    if major_minor > 0.44:
                        return True
                    else:
                        return False
            else:
                logging.warning("无法获取版本信息")
                return None

    except Exception as e:
        logging.error(f"检查版本失败: {str(e)}")
        return None


def reset_machine_id(greater_than_0_45):
    if greater_than_0_45:
        # 提示请手动执行脚本 https://github.com/chengazhen/cursor-auto-free/blob/main/patch_cursor_get_machine_id.py
        logging.info(
            f"{Fore.RED}请手动执行脚本 https://github.com/chengazhen/cursor-auto-free/blob/main/patch_cursor_get_machine_id.py{Style.RESET_ALL}"
        )
    else:
        MachineIDResetter().reset_machine_ids()


if __name__ == "__main__":
    print_logo()
    greater_than_0_45 = check_cursor_version()
    browser_manager = None
    try:
        logging.info("\n=== 初始化程序 ===")
        # 提示用户选择操作模式
        print("\n请选择操作模式:")
        print("1. 仅重置机器码")
        print("2. 完整注册流程")

        while True:
            try:
                choice = int(input("请输入选项 (1 或 2): ").strip())
                if choice in [1, 2]:
                    break
                else:
                    print("无效的选项,请重新输入")
            except ValueError:
                print("请输入有效的数字")

        if choice == 1:
            # 仅执行重置机器码
            reset_machine_id(greater_than_0_45)
            logging.info("机器码重置完成")
            sys.exit(0)

        # 小于0.45的版本需要打补丁
        if not greater_than_0_45:
            ExitCursor()
        logging.info("正在初始化浏览器...")

        # 获取user_agent
        user_agent = get_user_agent()
        if not user_agent:
            logging.error("获取user agent失败，使用默认值")
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        # 剔除user_agent中的"HeadlessChrome"
        user_agent = user_agent.replace("HeadlessChrome", "Chrome")

        browser_manager = BrowserManager()
        browser = browser_manager.init_browser(user_agent)

        # 获取并打印浏览器的user-agent
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")

        logging.info("正在初始化邮箱验证模块...")
        email_handler = EmailVerificationHandler()

        logging.info("\n=== 配置信息 ===")
        login_url = "https://authenticator.cursor.sh"
        sign_up_url = "https://authenticator.cursor.sh/sign-up"
        settings_url = "https://www.cursor.com/settings"
        mail_url = "https://tempmail.plus"

        logging.info("正在生成随机账号信息...")
        email_generator = EmailGenerator()
        account = email_generator.generate_email()
        password = email_generator.default_password
        first_name = email_generator.default_first_name
        last_name = email_generator.default_last_name

        logging.info(f"生成的邮箱账号: {account}")
        auto_update_cursor_auth = True

        tab = browser.latest_tab

        tab.run_js("try { turnstile.reset() } catch(e) { }")

        logging.info("\n=== 开始注册流程 ===")
        logging.info(f"正在访问登录页面: {login_url}")
        tab.get(login_url)

        if sign_up_account(browser, tab):
            logging.info("正在获取会话令牌...")
            token = get_cursor_session_token(tab)
            if token:
                logging.info("更新认证信息...")
                update_cursor_auth(
                    email=account, access_token=token, refresh_token=token
                )

                logging.info("重置机器码...")
                reset_machine_id(greater_than_0_45)
                logging.info("所有操作已完成")
            else:
                logging.error("获取会话令牌失败，注册流程未完成")

    except Exception as e:
        logging.error(f"程序执行出现错误: {str(e)}")
        import traceback

        logging.error(traceback.format_exc())
    finally:
        if browser_manager:
            browser_manager.quit()
        input("\n程序执行完毕，按回车键退出...")
