import type { Contact } from "@/lib/api";

type StoreContactsProps = {
  contacts: Contact[];
  /** Shown above the list; omitted where the surrounding block already says who this is. */
  heading?: string;
};

const LABEL: Record<Contact["platform"], string> = {
  phone: "Телефон",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  viber: "Viber",
  instagram: "Instagram",
  facebook: "Facebook",
};

// the handle reads as a handle, the number as a number
const AT_SIGN: ReadonlySet<Contact["platform"]> = new Set(["telegram", "instagram"]);

/** Dialling and messaging apps open in place; a profile page is a different site. */
function opensElsewhere(href: string): boolean {
  return href.startsWith("http://") || href.startsWith("https://");
}

function shown(contact: Contact): string {
  return AT_SIGN.has(contact.platform) ? `@${contact.value}` : contact.value;
}

/**
 * The only way to order in the MVP: there is no cart and no checkout, so these links are
 * what turns a product page into a sale. The addresses are built by the backend — the
 * page renders what it is given rather than guessing at each platform's URL shape.
 */
export function StoreContacts({ contacts, heading }: StoreContactsProps) {
  if (contacts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      {heading === undefined ? null : <p className="text-sm text-ink-muted">{heading}</p>}
      <ul className="flex flex-wrap gap-2">
        {contacts.map((contact) => (
          <li key={contact.platform}>
            <a
              href={contact.href}
              {...(opensElsewhere(contact.href)
                ? { target: "_blank", rel: "noopener noreferrer" }
                : {})}
              className="inline-flex items-baseline gap-2 rounded-card border border-ink-muted/20 px-3 py-2 text-sm transition hover:border-brand hover:text-brand"
            >
              <span className="text-ink-muted">{LABEL[contact.platform]}</span>
              <span className="font-medium">{shown(contact)}</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
