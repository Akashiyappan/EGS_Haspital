import { type FormEvent, useRef, useState } from 'react';
import { Link } from 'react-router';

import { FormField, SelectField } from '@/components/FormField';
import { Alert, Avatar, Card, PageHeader } from '@/components/ui';
import { useAuth } from '@/features/auth/useAuth';
import { useUpdateMe, useUploadAvatar } from '@/features/users/api';
import type { Me } from '@/features/users/types';
import { getErrorMessage } from '@/lib/errors';
import { useMeta } from '@/lib/hooks';
import { type Errors, hasErrors, validatePhone, validateRequired } from '@/lib/validation';

function ProfileForm({ user }: { user: Me }) {
  const update = useUpdateMe();
  const isPatient = user.role === 'PATIENT';
  const [values, setValues] = useState({
    first_name: user.first_name,
    last_name: user.last_name ?? '',
    phone: user.phone ?? '',
    date_of_birth: user.patient?.date_of_birth ?? '',
    gender: user.patient?.gender ?? '',
    emergency_contact_name: user.patient?.emergency_contact_name ?? '',
    emergency_contact_phone: user.patient?.emergency_contact_phone ?? '',
  });
  const [errors, setErrors] = useState<Errors<'first_name' | 'phone' | 'emergency_contact_phone'>>(
    {},
  );
  const [saved, setSaved] = useState(false);

  const set = (field: keyof typeof values) => (event: { target: { value: string } }) => {
    setSaved(false);
    setValues((v) => ({ ...v, [field]: event.target.value }));
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors = {
      first_name: validateRequired(values.first_name, 'First name'),
      phone: validatePhone(values.phone),
      emergency_contact_phone: validatePhone(values.emergency_contact_phone),
    };
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) return;
    const blankToNull = (value: string) => value.trim() || null;
    update.mutate(
      {
        first_name: values.first_name.trim(),
        last_name: blankToNull(values.last_name),
        phone: blankToNull(values.phone),
        ...(isPatient && {
          date_of_birth: values.date_of_birth || null,
          gender: blankToNull(values.gender),
          emergency_contact_name: blankToNull(values.emergency_contact_name),
          emergency_contact_phone: blankToNull(values.emergency_contact_phone),
        }),
      },
      { onSuccess: () => setSaved(true) },
    );
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      {saved && <Alert tone="success">Profile saved.</Alert>}
      {update.isError && <Alert>{getErrorMessage(update.error)}</Alert>}
      <div className="grid-2">
        <FormField
          label="First name"
          value={values.first_name}
          error={errors.first_name}
          maxLength={100}
          onChange={set('first_name')}
        />
        <FormField
          label="Last name"
          value={values.last_name}
          maxLength={100}
          onChange={set('last_name')}
        />
        <FormField
          label="Email"
          value={user.email}
          disabled
          hint="Contact the clinic to change your email."
        />
        <FormField
          label="Phone"
          type="tel"
          autoComplete="tel"
          value={values.phone}
          error={errors.phone}
          onChange={set('phone')}
        />
      </div>
      {isPatient && (
        <div className="grid-2">
          <FormField
            label="Date of birth"
            type="date"
            value={values.date_of_birth}
            onChange={set('date_of_birth')}
          />
          <SelectField label="Gender" value={values.gender} onChange={set('gender')}>
            <option value="">Prefer not to say</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </SelectField>
          <FormField
            label="Emergency contact name"
            value={values.emergency_contact_name}
            maxLength={200}
            onChange={set('emergency_contact_name')}
          />
          <FormField
            label="Emergency contact phone"
            type="tel"
            value={values.emergency_contact_phone}
            error={errors.emergency_contact_phone}
            onChange={set('emergency_contact_phone')}
          />
        </div>
      )}
      <div className="row">
        <button type="submit" disabled={update.isPending}>
          {update.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  );
}

export function AvatarUploader({
  name,
  url,
  onUpload,
  pending,
  error,
}: {
  name: string;
  url: string | null;
  onUpload: (file: File) => void;
  pending: boolean;
  error: unknown;
}) {
  const meta = useMeta();
  const input = useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  function pick(file: File | undefined) {
    if (!file) return;
    if (!meta.upload_allowed_types.includes(file.type)) {
      setLocalError('Choose a JPEG, PNG or WebP image.');
      return;
    }
    if (file.size > meta.upload_max_bytes) {
      setLocalError(
        `Images must be ${Math.round(meta.upload_max_bytes / 1024 / 1024)} MB or smaller.`,
      );
      return;
    }
    setLocalError(null);
    onUpload(file);
  }

  return (
    <div className="row wrap">
      <Avatar name={name} url={url} size={72} />
      <div className="stack small-gap">
        <input
          ref={input}
          type="file"
          hidden
          accept={meta.upload_allowed_types.join(',')}
          onChange={(event) => {
            pick(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
        <button
          type="button"
          className="secondary small"
          disabled={pending || !meta.uploads_enabled}
          onClick={() => input.current?.click()}
        >
          {pending ? 'Uploading…' : 'Change photo'}
        </button>
        {!meta.uploads_enabled && (
          <span className="muted small-text">Uploads are not configured.</span>
        )}
        {localError || error ? (
          <span className="field-error">{localError ?? getErrorMessage(error)}</span>
        ) : null}
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { user } = useAuth();
  const upload = useUploadAvatar();
  if (!user) return null;
  return (
    <div className="stack">
      <PageHeader title="Profile" description="Your personal details." />
      <Card title="Photo">
        <AvatarUploader
          name={user.full_name}
          url={user.avatar_url}
          onUpload={(file) => upload.mutate(file)}
          pending={upload.isPending}
          error={upload.error}
        />
      </Card>
      <Card title="Details">
        <ProfileForm key={user.id} user={user} />
      </Card>
      <Card title="Security">
        <Link to="/change-password" className="button secondary">
          Change password
        </Link>
      </Card>
    </div>
  );
}
