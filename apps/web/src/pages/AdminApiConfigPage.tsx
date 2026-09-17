import { Alert, Button, Card, Form, Input, Radio, Select, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { api, type AdminApiConfig } from '../utils/api';
import { toast } from '../utils/toast';

type FormValues = {
  provider: 'mock' | 'deepseek';
  api_key?: string;
  base_url: string;
  model: string;
  model_pro: string;
  thinking: 'disabled' | 'enabled' | 'auto';
  github_publication_enabled: boolean;
  github_token?: string;
};

export default function AdminApiConfigPage() {
  const [form] = Form.useForm<FormValues>();
  const [config, setConfig] = useState<AdminApiConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true); setError('');
    void api.adminApiConfig().then((value) => {
      setConfig(value);
      form.setFieldsValue({
        provider: value.provider,
        base_url: value.base_url,
        model: value.model,
        model_pro: value.model_pro,
        thinking: value.thinking,
        github_publication_enabled: value.github_publication_enabled,
      });
    }).catch((failure) => setError(failure instanceof Error ? failure.message : 'API 配置载入失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const save = async (values: FormValues) => {
    setSaving(true); setError('');
    try {
      const next = await api.saveAdminApiConfig({
        ...values,
        ...(values.api_key?.trim() ? { api_key: values.api_key.trim() } : {}),
        ...(values.github_token?.trim() ? { github_token: values.github_token.trim() } : {}),
      });
      setConfig(next); form.resetFields(['api_key', 'github_token']);
      toast.success('统一 API 配置已保存；新请求会使用当前配置');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'API 配置保存失败');
    } finally { setSaving(false); }
  };

  if (loading) return <div className="chrono-page-loading"><Spin /><span>正在读取 API 配置…</span></div>;
  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      <Card title="统一 AI / API 配置" extra={config?.api_key_configured ? <Tag color="green">已配置密钥</Tag> : <Tag>未配置密钥</Tag>}>
        <Typography.Paragraph type="secondary">
          练、问、创和旧版兼容问答共用这里的模型配置。密钥只保存在本地课堂数据库，不会回显、写入 Pages 或提交 Git。
        </Typography.Paragraph>
        {error ? <Alert type="error" showIcon message={error} action={<Button onClick={load}>重试</Button>} /> : null}
        <Form<FormValues> form={form} layout="vertical" onFinish={save}>
          <Form.Item name="provider" label="服务提供方" rules={[{ required: true }]}>
            <Radio.Group options={[{ label: '离线 Mock', value: 'mock' }, { label: 'DeepSeek 在线', value: 'deepseek' }]} />
          </Form.Item>
          <Form.Item name="api_key" label={`API 密钥（留空保持当前 ${config?.api_key_last4 ? `末四位 ${config.api_key_last4}` : '未配置'}）`}>
            <Input.Password placeholder="只在需要更换密钥时填写" autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="base_url" label="API 地址" rules={[{ required: true, type: 'url' }]}>
            <Input />
          </Form.Item>
          <Space.Compact block>
            <Form.Item name="model" label="快速模型" style={{ width: '50%' }} rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="model_pro" label="高质量模型" style={{ width: '50%' }} rules={[{ required: true }]}><Input /></Form.Item>
          </Space.Compact>
          <Form.Item name="thinking" label="思考模式" rules={[{ required: true }]}> 
            <Select options={[{ label: '关闭（课堂响应更快）', value: 'disabled' }, { label: '自动', value: 'auto' }, { label: '开启', value: 'enabled' }]} />
          </Form.Item>
          <Card size="small" title="教师内容仓库（GitHub）" style={{ marginBottom: 16 }}>
            <Typography.Paragraph type="secondary">
              当前发布目标自动读取课程内容仓库绑定；这里仅维护服务端使用的仓库令牌，不会写入前端、Pages 或 Git。
              当前目标：{config?.github_repository || '未读取到仓库绑定'}。
            </Typography.Paragraph>
            <Form.Item name="github_publication_enabled" label="启用教师仓库发布">
              <Radio.Group options={[{ label: '关闭', value: false }, { label: '启用', value: true }]} optionType="button" />
            </Form.Item>
            <Form.Item name="github_token" label={`GitHub 仓库令牌（留空保持当前 ${config?.github_token_last4 ? `末四位 ${config.github_token_last4}` : '未配置'}）`}>
              <Input.Password placeholder="仅在需要更换令牌时填写" autoComplete="new-password" />
            </Form.Item>
            <Typography.Text type="secondary">启用后教师端发布动作才会使用该令牌；未配置令牌时发布会被安全拒绝。</Typography.Text>
          </Card>
          <Button type="primary" htmlType="submit" loading={saving}>保存统一配置</Button>
        </Form>
      </Card>
    </div>
  );
}
