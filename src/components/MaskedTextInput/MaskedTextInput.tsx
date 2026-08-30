/**
 * Linux 适配的掩码输入框（替代 antd Input.Password）。
 *
 * 背景：WebKitGTK（Linux）上 `type="password"` 输入框在 fcitx5 + Wayland 组合下
 * 会吞掉按键（掩码状态无法输入，WebKit/输入法已知兼容性问题）。
 *
 * 方案：改用普通文本框 + CSS `-webkit-text-security: disc` 实现圆点掩码，
 * 引擎层面不再是密码字段，彻底绕开该类问题；提供眼睛按钮切换明文。
 * API 与 antd `Input.Password` 的常用子集兼容，可直接替换。
 */

import { forwardRef, useState } from 'react';
import { Input } from 'antd';
import type { InputProps, InputRef } from 'antd';
import { EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';

export interface MaskedTextInputProps extends InputProps {
  /** 是否默认明文显示（默认掩码圆点） */
  defaultVisible?: boolean;
}

const MaskedTextInput = forwardRef<InputRef, MaskedTextInputProps>((props, ref) => {
  const { defaultVisible = false, suffix, style, ...rest } = props;
  const [visible, setVisible] = useState(defaultVisible);

  return (
    <Input
      {...rest}
      ref={ref}
      type="text"
      spellCheck={rest.spellCheck ?? false}
      autoComplete={rest.autoComplete ?? 'off'}
      style={
        {
          ...style,
          // 掩码圆点伪装；visible 时恢复普通文本
          WebkitTextSecurity: visible ? 'none' : 'disc',
        } as React.CSSProperties
      }
      suffix={
        <>
          {suffix}
          {/* onMouseDown preventDefault：点击眼睛时不让输入框失焦 */}
          <span
            role="button"
            tabIndex={-1}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => setVisible((v) => !v)}
            style={{
              cursor: 'pointer',
              opacity: 0.45,
              display: 'inline-flex',
              alignItems: 'center',
              userSelect: 'none',
            }}
          >
            {visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
          </span>
        </>
      }
    />
  );
});

MaskedTextInput.displayName = 'MaskedTextInput';

export default MaskedTextInput;
