import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "@/components/auth/Field";

/**
 * One labelled input, used by every form on the platform.
 *
 * Which makes its accessibility the platform's accessibility: the label has to belong to the
 * input, and a refusal has to be something a screen reader announces rather than a red line
 * only a sighted person notices. `aria-invalid` and `role="alert"` are what do that, and both
 * are the kind of attribute that disappears in a refactor without anything looking broken.
 */

describe("Field", () => {
  it("belongs to its label, so clicking the words focuses the box", () => {
    render(<Field label="Электронная почта" name="email" />);

    expect(screen.getByLabelText("Электронная почта")).toHaveAttribute("name", "email");
  });

  it("is a text box unless it is told otherwise", () => {
    render(<Field label="Электронная почта" name="email" />);

    expect(screen.getByLabelText("Электронная почта")).toHaveAttribute("type", "text");
  });

  it("hides what is typed when it is a password", () => {
    render(<Field label="Пароль" name="password" type="password" />);

    expect(screen.getByLabelText("Пароль")).toHaveAttribute("type", "password");
  });

  it("is required unless the form says the answer is optional", () => {
    render(<Field label="Телефон" name="phone" />);
    expect(screen.getByLabelText("Телефон")).toBeRequired();

    render(<Field label="Телефон ещё раз" name="phone2" required={false} />);
    expect(screen.getByLabelText("Телефон ещё раз")).not.toBeRequired();
  });

  it("tells the browser what it is, so a password manager can fill it", () => {
    render(<Field label="Пароль" name="password" autoComplete="current-password" />);

    expect(screen.getByLabelText("Пароль")).toHaveAttribute("autocomplete", "current-password");
  });

  it("keeps what the person already had when a form is reopened", () => {
    render(<Field label="Название" name="display_name" defaultValue="Ромашка" />);

    expect(screen.getByLabelText("Название")).toHaveValue("Ромашка");
  });

  it("says nothing about validity while nothing is wrong", () => {
    render(<Field label="Электронная почта" name="email" />);

    const input = screen.getByLabelText("Электронная почта");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("announces a refusal instead of only colouring it", () => {
    render(<Field label="Электронная почта" name="email" error="Этот адрес уже занят" />);

    const input = screen.getByLabelText("Электронная почта");
    expect(input).toBeInvalid();
    expect(screen.getByRole("alert")).toHaveTextContent("Этот адрес уже занят");
  });

  it("points the input at the message, so the two are read together", () => {
    render(<Field label="Электронная почта" name="email" error="Этот адрес уже занят" />);

    expect(screen.getByLabelText("Электронная почта")).toHaveAccessibleDescription(
      "Этот адрес уже занят",
    );
  });
});
