create table if not exists chats (
    id uuid primary key default gen_random_uuid(),
    title text not null default 'New conversation',
    citations jsonb not null default '[]',
    created_at timestamptz not null default now()
);

alter table chats add column if not exists citations jsonb not null default '[]';

create table if not exists exchanges (
    id bigint generated always as identity primary key,
    chat_id uuid not null references chats(id) on delete cascade,
    user_text text not null,
    assistant_text text not null,
    sources jsonb not null default '[]',
    model_messages jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists exchanges_chat_idx on exchanges (chat_id, id);

-- Single demo portfolio: one meta row, positions keyed by ticker.
create table if not exists portfolio (
    single_row boolean primary key default true check (single_row),
    cash double precision not null,
    currency text not null,
    as_of date not null
);

create table if not exists positions (
    id bigint generated always as identity primary key,
    ticker text not null unique,
    name text not null,
    quantity double precision not null,
    cost_basis double precision not null,
    currency text not null
);
