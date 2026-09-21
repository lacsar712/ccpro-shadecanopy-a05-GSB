from rest_framework.exceptions import APIException


class Conflict(APIException):
    """HTTP 409：移栽窗口冲突 / 窗口内新建轮灌被拦截。"""

    status_code = 409
    default_code = "conflict"
    default_detail = "操作与移栽窗口冲突"
