"""
文件读写工具模块 - 统一处理编码问题

提供健壮的文件读写函数，自动处理各种编码格式。
"""

import os

# 编码尝试顺序
_ENCODINGS = ['utf-8-sig', 'utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'latin-1']


def read_text_file(filepath: str, fallback_errors: str = 'replace') -> str:
    """
    读取文本文件，自动检测编码并处理解码错误。
    
    Args:
        filepath: 文件路径
        fallback_errors: 编码错误处理方式 ('replace', 'ignore', 'strict')
    
    Returns:
        文件内容字符串
    
    Raises:
        FileNotFoundError: 文件不存在
        OSError: 其他文件操作错误
    """
    for encoding in _ENCODINGS:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    
    with open(filepath, 'r', encoding='utf-8', errors=fallback_errors) as f:
        return f.read()


def write_text_file(filepath: str, content: str, encoding: str = 'utf-8', 
                    errors: str = 'replace') -> None:
    """
    写入文本文件，确保编码正确。
    
    Args:
        filepath: 文件路径
        content: 要写入的内容
        encoding: 目标编码
        errors: 编码错误处理方式
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding=encoding, errors=errors) as f:
        f.write(content)


def append_text_file(filepath: str, content: str, encoding: str = 'utf-8', 
                     errors: str = 'replace') -> None:
    """
    追加内容到文本文件。
    
    Args:
        filepath: 文件路径
        content: 要追加的内容
        encoding: 目标编码
        errors: 编码错误处理方式
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'a', encoding=encoding, errors=errors) as f:
        f.write(content)


def read_json_file(filepath: str) -> dict:
    """
    读取 JSON 文件，自动处理编码问题。
    
    Args:
        filepath: 文件路径
    
    Returns:
        JSON 数据字典
    """
    import json
    content = read_text_file(filepath)
    return json.loads(content)


def write_json_file(filepath: str, data: dict, indent: int = 2) -> None:
    """
    写入 JSON 文件。
    
    Args:
        filepath: 文件路径
        data: 要写入的数据
        indent: 缩进空格数
    """
    import json
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    write_text_file(filepath, content)
