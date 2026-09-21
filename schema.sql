-- Fresh-install schema. Run once via `python init_db.py`.
--
-- For an EXISTING database, run `python migrate.py` instead: it inspects the
-- current state before each change and is safe to re-run. This file used to
-- carry a tail of bare ALTER TABLE statements, which meant re-running
-- init_db.py against a live database failed on the first already-applied one.
--
-- There are deliberately no archived_income / archived_expense tables here.
-- Months are derived from the `date` column now; nothing is moved between
-- tables at month end.

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    avatar_filename VARCHAR(255) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS income (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    source VARCHAR(100) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    date DATE NULL,
    INDEX idx_income_user_date (user_id, date)
);

CREATE TABLE IF NOT EXISTS expense (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    category VARCHAR(50) NOT NULL,
    note TEXT,
    date DATE NOT NULL,
    attachment VARCHAR(255) DEFAULT NULL,
    done_by VARCHAR(50) NOT NULL DEFAULT 'Self',
    INDEX idx_expense_user_date (user_id, date),
    INDEX idx_expense_user_category (user_id, category)
);

CREATE TABLE IF NOT EXISTS setting (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    monthly_limit DECIMAL(10, 2) NOT NULL DEFAULT 0.0,
    -- Opening balance. Live savings is this plus SUM(income) - SUM(expense).
    total_savings DECIMAL(10, 2) DEFAULT 0.0,
    default_done_by VARCHAR(50) DEFAULT NULL,
    use_automated_income TINYINT(1) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    icon VARCHAR(50) NULL,
    color VARCHAR(20) NULL,
    UNIQUE KEY user_category_unique (user_id, name)
);

CREATE TABLE IF NOT EXISTS household_member (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    UNIQUE KEY user_member_unique (user_id, name)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    actor VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INT NULL,
    action VARCHAR(10) NOT NULL,
    before_json JSON NULL,
    after_json JSON NULL,
    undoes_log_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_user_entity (user_id, entity_type, entity_id)
);
