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
      });
      setConfig(next); form.resetFields(['api_key']);
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
          <Button type="primary" htmlType="submit" loading={saving}>保存统一配置</Button>
        </Form>
      </Card>
    </div>
  );
}
