# -*- coding: utf-8 -*-
import logging
import re
import tempfile
import time

import pywinauto
from pywinauto.findwindows import WindowNotFoundError

from easytrader.clienttrader import clienttrader
from easytrader.strategy import grid_strategies
from easytrader.utils.captcha import recognize_verify_code

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class THS519ClientTrader(clienttrader.BaseLoginClientTrader):
    """
    同花顺v5.19.15.133的实现(xiadan.exe)
    和5.18的界面相比，发生了变化，需要重新子类化
    """

    grid_strategy = grid_strategies.Copy

    @property
    def broker_type(self):
        return "ths5.19"

    # @property
    # def balance(self):
    #     self._switch_left_menus(["查询[F4]", "资金股票"])

    #     return self._get_grid_data(self._config.COMMON_GRID_CONTROL_ID_NEW)

    def login(self, user, password, exe_path, comm_password=None, **kwargs):
        """
        登陆客户端

        :param user: 账号
        :param password: 明文密码
        :param exe_path: 客户端路径类似 'C:\\中国银河证券双子星3.2\\Binarystar.exe',
            默认 'C:\\中国银河证券双子星3.2\\Binarystar.exe'
        :param comm_password: 通讯密码, 华泰需要，可不设
        :return:
        """
        try:
            # 尝试连接一下，难道一定要等触发异常？？？
            logger.info("尝试连接到原有进程")
            self._app = pywinauto.Application().connect(
                path=self._run_exe_path(exe_path), timeout=1
            )
            logger.info("尝试连接到原有进程[%s]成功", exe_path)

        # pylint: disable=broad-except
        except Exception:
            logger.info("尝试连接到原有进程失败，重新启动软件：%s", exe_path)
            self._app = pywinauto.Application().start(exe_path)

            # wait login window ready
            logger.info("启动软件完毕，等待登录窗口出现")
            while True:
                try:
                    login_window = self._app.top_window()
                    login_window.Edit1.wait("ready")
                    break
                except WindowNotFoundError:
                    logger.debug(".")
                    time.sleep(1)

            logger.info("登录窗口出现，准备输入用户名和密码")
            logger.info("自动输入：用户[%s]、密码[%s]", user, password[:2] + "****")
            login_window.Edit1.set_focus()
            login_window.Edit1.type_keys(user)
            logger.debug("用户名控件ID：%s", login_window.Edit1.control_id())
            login_window.Edit2.set_focus()
            login_window.Edit2.type_keys(password)
            logger.debug("密码控件ID：%s", login_window.Edit2.control_id())

            # 处理验证码
            verify_code_result = self._handle_verify_code_input(login_window)
            if verify_code_result == 1:  # 没有验证码控件
                # 直接点击登录
                self._app.top_window()["登录"].click()
                # 等待登录窗口消失
                self._app.top_window().wait_not("exists", 5)
            elif verify_code_result == 2:  # 验证码输入失败
                logger.error("验证码输入失败，登录终止")
                return False
            # verify_code_result == 0 时验证码输入成功，不需要额外操作

            logger.debug("启动成功...")
            self._app = pywinauto.Application().connect(
                path=self._run_exe_path(exe_path), timeout=10
            )
        logger.debug("主窗口：%r", self._app.window(title="网上股票交易系统5.0"))
        self._main = self._app.window(title="网上股票交易系统5.0")

    def _handle_verify_code_input(self, login_window):
        """处理验证码输入

        Args:
            login_window: 登录窗口
            login_window_handle: 登录窗口句柄

        Returns:
            int: 验证码处理结果
                0: 成功
                1: 没有找到验证码控件（不需要验证码）
                2: 验证码输入多次失败
        """
        try:
            # 获取所有控件的详细信息
            win_children = login_window.children()
            # 过滤出Edit控件
            edit_ctrls = [
                child
                for child in win_children
                if child.class_name() == "Edit"
                and child.is_visible()
                and child.is_enabled()
            ]

            logger.debug(f"找到的Edit控件数量: {len(edit_ctrls)}")

            if len(edit_ctrls) == 2:
                logger.info("没有找到验证码控件，跳过验证码输入")
                return 1  # 没有验证码控件

            # 找到用户名和密码之外的Edit控件
            verify_ctrl = None
            for ctrl in edit_ctrls:
                if ctrl.control_id() not in [
                    login_window.Edit1.control_id(),
                    login_window.Edit2.control_id(),
                ]:
                    logger.debug("控件ID:%s", ctrl.control_id())
                    verify_ctrl = ctrl
                    break

            if verify_ctrl is None:
                logger.info("没有找到验证码控件，跳过验证码输入")
                return 1  # 没有验证码控件

            logger.info("找到验证码控件，准备输入验证码")
            retry = 0
            while retry < 5:
                try:
                    verify_ctrl.set_focus()
                    logger.info("清除上一次输入的验证码")
                    verify_ctrl.type_keys("^a{BACKSPACE}")
                    time.sleep(1)
                    code = self._handle_verify_code()
                    verify_ctrl.type_keys(code)
                    logger.info("解析验证码解析成功，并输入到Edit框：%s", code)
                    time.sleep(1)
                    # 点击右侧的确定按钮来登录
                    self._app.top_window()["登录"].click()
                    # 等待登录窗口消失
                    self._app.top_window().wait_not("exists", 30)
                    return 0  # 成功
                except Exception:
                    time.sleep(1)
                    logger.debug("登录失败，再一次尝试")
                    retry += 1

            logger.error("验证码输入多次失败")
            return 2  # 验证码输入失败
        except Exception:
            logger.info("验证码处理发生异常")
            return 2  # 验证码处理异常

    def _handle_verify_code(self):
        control = self._app.top_window().window(control_id=0x5DB)
        control.click()
        time.sleep(0.2)
        file_path = tempfile.mktemp() + ".jpg"
        # 新版同花顺的登录验证码居然是分成了2部分，3个数字+1个数字，很恶心，需要hack一下宽度，扩大一些来存图片
        rect = control.rectangle()
        height = rect.bottom - rect.top
        rect.right += height
        control.capture_as_image(rect).save(file_path)
        time.sleep(0.2)
        vcode = recognize_verify_code(file_path)
        logger.debug("验证码识别结果：%s", vcode)
        return "".join(re.findall("[a-zA-Z0-9]+", vcode))
