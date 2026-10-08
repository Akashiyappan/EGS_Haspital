import { type FormEvent, useState } from 'react';

import { FormField, TextAreaField } from '@/components/FormField';
import { Alert } from '@/components/ui';
import { getErrorMessage } from '@/lib/errors';
import type { DoctorAdmin } from '@/lib/types';
import {
  type Errors,
  hasErrors,
  validateEmail,
  validatePassword,
  validatePhone,
  validateRequired,
} from '@/lib/validation';

import { type DoctorInput, useAdminSpecializations, useSaveDoctor } from './api';

type Field =
  | 'first_name'
  | 'email'
  | 'temporary_password'
  | 'phone'
  | 'specialization_ids'
  | 'experience_years';

export function DoctorForm({
  doctor,
  onSaved,
}: {
  doctor?: DoctorAdmin;
  onSaved: (doctor: DoctorAdmin) => void;
}) {
  const isEdit = !!doctor;
  const specializations = useAdminSpecializations();
  const save = useSaveDoctor(doctor?.id);
  const [values, setValues] = useState({
    first_name: doctor?.first_name ?? '',
    last_name: doctor?.last_name ?? '',
    email: doctor?.email ?? '',
    temporary_password: '',
    phone: doctor?.phone ?? '',
    qualification: doctor?.qualification ?? '',
    experience_years: String(doctor?.experience_years ?? 0),
    bio: doctor?.bio ?? '',
  });
  const [selected, setSelected] = useState<number[]>(
    doctor?.specializations.map((s) => s.id) ?? [],
  );
  const [errors, setErrors] = useState<Errors<Field>>({});

  const set = (field: keyof typeof values) => (event: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [field]: event.target.value }));

  function toggle(id: number) {
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const years = Number(values.experience_years);
    const nextErrors: Errors<Field> = {
      first_name: validateRequired(values.first_name, 'First name'),
      email: isEdit ? undefined : validateEmail(values.email),
      temporary_password: isEdit ? undefined : validatePassword(values.temporary_password),
      phone: validatePhone(values.phone),
      specialization_ids: selected.length ? undefined : 'Choose at least one specialization',
      experience_years:
        Number.isInteger(years) && years >= 0 && years <= 80 ? undefined : 'Enter 0–80 years',
    };
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) return;

    const payload: DoctorInput = {
      first_name: values.first_name.trim(),
      last_name: values.last_name.trim() || null,
      phone: values.phone.trim() || null,
      qualification: values.qualification.trim() || null,
      experience_years: years,
      bio: values.bio.trim() || null,
      specialization_ids: selected,
      ...(!isEdit && { email: values.email.trim(), temporary_password: values.temporary_password }),
    };
    save.mutate(payload, { onSuccess: onSaved });
  }

  const options = specializations.data?.filter((s) => s.is_active || selected.includes(s.id)) ?? [];

  return (
    <form className="stack" onSubmit={submit} noValidate>
      {save.isError && <Alert>{getErrorMessage(save.error)}</Alert>}
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
          type="email"
          value={values.email}
          error={errors.email}
          disabled={isEdit}
          hint={isEdit ? 'Email cannot be changed.' : undefined}
          onChange={set('email')}
        />
        <FormField
          label="Phone"
          type="tel"
          value={values.phone}
          error={errors.phone}
          onChange={set('phone')}
        />
        {!isEdit && (
          <FormField
            label="Temporary password"
            type="password"
            autoComplete="new-password"
            value={values.temporary_password}
            error={errors.temporary_password}
            hint="Share it securely. The doctor must change it at first sign-in; it is never shown again."
            onChange={set('temporary_password')}
          />
        )}
        <FormField
          label="Qualification"
          value={values.qualification}
          maxLength={255}
          onChange={set('qualification')}
        />
        <FormField
          label="Experience (years)"
          type="number"
          min={0}
          max={80}
          value={values.experience_years}
          error={errors.experience_years}
          onChange={set('experience_years')}
        />
      </div>
      <fieldset className="field">
        <legend>Specializations</legend>
        <div className="chips">
          {options.map((s) => (
            <label
              key={s.id}
              className={selected.includes(s.id) ? 'chip chip-check checked' : 'chip chip-check'}
            >
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={() => toggle(s.id)}
              />
              {s.name}
            </label>
          ))}
          {!options.length && (
            <span className="muted small-text">Create specializations first.</span>
          )}
        </div>
        {errors.specialization_ids && (
          <span className="field-error">{errors.specialization_ids}</span>
        )}
      </fieldset>
      <TextAreaField
        label="Bio"
        rows={4}
        maxLength={2000}
        value={values.bio}
        onChange={set('bio')}
      />
      <div className="row">
        <button type="submit" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create doctor'}
        </button>
      </div>
    </form>
  );
}
