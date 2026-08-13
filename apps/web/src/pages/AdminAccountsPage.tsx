import {
  CheckCircleOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  TeamOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { authApi } from '../auth/client';
import {
  ROLE_LABELS,
  type UserAccount,
  type UserRole,
} from '../auth/types';
import { ApiError } from '../utils/api';
import { toast } from '../utils/toast';

const ROLE_OPTIONS: Array<{ label: string; value: UserRole }> = (
  Object.entries(ROLE_LABELS) as Array<[UserRole, string]>
).map(([value, label]) => ({ value, label }));

interface AccountFormValues {
  username: string;
  display_name: string;
  password: string;
  roles: UserRole[];
}

interface EditFormValues {
  display_name: string;
  roles: UserRole[];
}

function formatAccountError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'last_admin_required') return '系统必须保留至少一名启用的管理员。';
    if (error.status === 403) return '当前账号没有账户管理权限。';
    if (error.status === 409) return error.message.replace(/^409\s+/, '');
  }
  return error instanceof Error ? error.message : '账户操作失败';
}

function roleTags(roles: UserRole[]) {
  const colors: Record<UserRole, string> = {
    student: 'cyan',
    teacher: 'geekblue',
    reviewer: 'gold',
    admin: 'volcano',
  };
  return roles.map((role) => (
    <Tag key={role} color={colors[role]}>{ROLE_LABELS[role]}</Tag>
  ));
}

export default function AdminAccountsPage() {
  const auth = useAuth();
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserAccount | null>(null);
  const [passwordUser, setPasswordUser] = useState<UserAccount | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createForm] = Form.useForm<AccountFormValues>();
  const [editForm] = Form.useForm<EditFormValues>();
  const [passwordForm] = Form.useForm<{ password: string }>();

  const loadUsers = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const response = await authApi.users(signal);
      setUsers(response.items);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      toast.error(formatAccountError(error));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadUsers(controller.signal);
    return () => controller.abort();
  }, [loadUsers]);

  const counts = useMemo(() => ({
    total: users.length,
    enabled: users.filter((user) => user.enabled).length,
    students: users.filter((user) => user.roles.includes('student') && user.enabled).length,
    staff: users.filter((user) => user.roles.some((role) => role !== 'student') && user.enabled).length,
  }), [users]);

  const createAccount = async (values: AccountFormValues) => {
    setSubmitting(true);
    try {
      await authApi.createUser(values);
      toast.success(`已创建账号 ${values.username}`);
      createForm.resetFields();
      setCreateOpen(false);
      await loadUsers();
    } catch (error) {
      toast.error(formatAccountError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const openEdit = (user: UserAccount) => {
    setEditUser(user);
    editForm.setFieldsValue({ display_name: user.display_name, roles: user.roles });
  };

  const saveAccount = async (values: EditFormValues) => {
    if (!editUser) return;
    setSubmitting(true);
    try {
      await authApi.updateUser(editUser.user_id, values);
      toast.success(`已更新 ${editUser.username} 的角色与称呼`);
      setEditUser(null);
      await loadUsers();
    } catch (error) {
      toast.error(formatAccountError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const setEnabled = async (user: UserAccount, enabled: boolean) => {
    setBusyUserId(user.user_id);
    try {
      await authApi.updateUser(user.user_id, { enabled });
      toast.success(enabled ? '账号已启用' : '账号已禁用，现有会话同时失效');
      await loadUsers();
    } catch (error) {
      toast.error(formatAccountError(error));
    } finally {
      setBusyUserId('');
    }
  };

  const resetPassword = async ({ password }: { password: string }) => {
    if (!passwordUser) return;
    setSubmitting(true);
    try {
      await authApi.resetPassword(passwordUser.user_id, password);
      toast.success(`已重置 ${passwordUser.username} 的密码，旧会话已失效`);
      passwordForm.resetFields();
      setPasswordUser(null);
      await loadUsers();
    } catch (error) {
      toast.error(formatAccountError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const revokeSessions = async (user: UserAccount) => {
    setBusyUserId(user.user_id);
    try {
      const response = await authApi.revokeUserSessions(user.user_id);
      toast.success(`已撤销 ${response.revoked_sessions} 个会话`);
      if (user.user_id === auth.principal?.user_id) auth.invalidate();
    } catch (error) {
      toast.error(formatAccountError(error));
    } finally {
      setBusyUserId('');
    }
  };

  const columns: ColumnsType<UserAccount> = [
    {
      title: '课堂身份',
      key: 'identity',
      fixed: 'left',
      width: 230,
      render: (_, user) => (
        <Space direction="vertical" size={1}>
          <Space size={6}>
            <strong>{user.display_name}</strong>
            {user.user_id === auth.principal?.user_id && <Tag>当前账号</Tag>}
          </Space>
          <span className="chrono-account-username">@{user.username}</span>
        </Space>
      ),
    },
    {
      title: '角色',
      dataIndex: 'roles',
      width: 260,
      render: (roles: UserRole[]) => <Space size={[0, 4]} wrap>{roleTags(roles)}</Space>,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 110,
      render: (enabled: boolean) => enabled
        ? <Tag icon={<CheckCircleOutlined />} color="success">启用</Tag>
        : <Tag icon={<StopOutlined />}>禁用</Tag>,
    },
    {
      title: '认证版本',
      dataIndex: 'auth_version',
      width: 110,
      render: (version: number) => `v${version}`,
    },
    {
      title: '操作',
      key: 'actions',
      width: 350,
      render: (_, user) => (
        <Space wrap>
          <Button size="small" icon={<UserSwitchOutlined />} onClick={() => openEdit(user)}>
            角色
          </Button>
          <Button
            size="small"
            icon={<KeyOutlined />}
            onClick={() => {
              setPasswordUser(user);
              passwordForm.resetFields();
            }}
          >
            改密
          </Button>
          <Popconfirm
            title={user.enabled ? '禁用这个账号？' : '重新启用这个账号？'}
            description={user.enabled ? '禁用后，该账号的全部会话会立即失效。' : '启用后可重新登录。'}
            onConfirm={() => void setEnabled(user, !user.enabled)}
          >
            <Button size="small" danger={user.enabled} loading={busyUserId === user.user_id}>
              {user.enabled ? '禁用' : '启用'}
            </Button>
          </Popconfirm>
          <Popconfirm
            title="撤销全部会话？"
            description="已登录设备需要重新输入密码。"
            onConfirm={() => void revokeSessions(user)}
          >
            <Button size="small" loading={busyUserId === user.user_id}>撤销会话</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="chrono-page chrono-accounts-page" data-testid="account-management">
      <div className="chrono-admin-heading">
        <div>
          <div className="chrono-course-eyeline">
            <span>ADMIN</span><span>统一账户</span><span>真实角色权限</span>
          </div>
          <h1 className="chrono-title">课堂账户与角色</h1>
          <p>创建课堂身份、分配职责并在需要时立即撤销会话。密码与令牌从不显示在列表中。</p>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadUsers()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>创建账号</Button>
        </Space>
      </div>

      <Row gutter={[12, 12]} className="chrono-account-stats">
        <Col xs={12} lg={6}><Card><Statistic title="全部账号" value={counts.total} prefix={<TeamOutlined />} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="当前启用" value={counts.enabled} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="学生" value={counts.students} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="教研与管理" value={counts.staff} prefix={<SafetyCertificateOutlined />} /></Card></Col>
      </Row>

      <Alert
        className="chrono-account-boundary"
        type="info"
        showIcon
        message="职责边界"
        description="学生进入课程与个人成果；教师创作；审校者独立审核；管理员发布课程并管理账户。服务端会再次校验每个动作，界面隐藏不等于授权。"
      />

      <Table<UserAccount>
        rowKey="user_id"
        loading={loading}
        columns={columns}
        dataSource={users}
        scroll={{ x: 1080 }}
        pagination={{ pageSize: 10, showSizeChanger: false }}
      />

      <Modal
        title="创建课堂账号"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        confirmLoading={submitting}
        onOk={() => createForm.submit()}
        destroyOnHidden
      >
        <Form<AccountFormValues>
          form={createForm}
          layout="vertical"
          initialValues={{ roles: ['student'] }}
          onFinish={createAccount}
        >
          <Form.Item label="登录账号" name="username" rules={[
            { required: true, message: '请输入登录账号' },
            { min: 3, max: 64, message: '账号长度为 3–64 个字符' },
            { pattern: /^[a-z0-9][a-z0-9._-]+$/, message: '使用小写字母、数字、点、下划线或短横线' },
          ]}>
            <Input autoComplete="off" placeholder="student.dayu" />
          </Form.Item>
          <Form.Item label="显示名称" name="display_name" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input autoComplete="off" placeholder="七年级学生 01" />
          </Form.Item>
          <Form.Item label="初始密码" name="password" rules={[
            { required: true, message: '请输入初始密码' },
            { min: 12, message: '密码至少 12 个字符' },
          ]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item label="角色" name="roles" rules={[{ required: true, message: '至少分配一个角色' }]}>
            <Checkbox.Group options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑角色 · ${editUser?.username || ''}`}
        open={Boolean(editUser)}
        onCancel={() => setEditUser(null)}
        okText="保存"
        confirmLoading={submitting}
        onOk={() => editForm.submit()}
        destroyOnHidden
      >
        <Form<EditFormValues> form={editForm} layout="vertical" onFinish={saveAccount}>
          <Form.Item label="显示名称" name="display_name" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            label="角色"
            name="roles"
            rules={[{ required: true, message: '至少分配一个角色' }]}
            extra="多角色账号同时拥有对应权限；内容自审限制仍由服务端执行。"
          >
            <Checkbox.Group options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码 · ${passwordUser?.username || ''}`}
        open={Boolean(passwordUser)}
        onCancel={() => setPasswordUser(null)}
        okText="重置并撤销旧会话"
        confirmLoading={submitting}
        onOk={() => passwordForm.submit()}
        destroyOnHidden
      >
        <Form<{ password: string }> form={passwordForm} layout="vertical" onFinish={resetPassword}>
          <Form.Item
            label="新密码"
            name="password"
            rules={[{ required: true, message: '请输入新密码' }, { min: 12, message: '密码至少 12 个字符' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Tooltip title="密码只会提交给当前课堂服务，不会写入浏览器存储。">
            <span className="chrono-account-help">重置后，目标账号需在所有设备重新登录。</span>
          </Tooltip>
        </Form>
      </Modal>
    </div>
  );
}
