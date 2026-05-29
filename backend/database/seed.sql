-- Default seed data (applied once when tables are empty)

INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at)
VALUES ('default', 10000.0, datetime('now'));

INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES
    (lower(hex(randomblob(16))), 'default', 'AAPL',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'GOOGL', datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'MSFT',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'AMZN',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'TSLA',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'NVDA',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'META',  datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'JPM',   datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'V',     datetime('now')),
    (lower(hex(randomblob(16))), 'default', 'NFLX',  datetime('now'));
