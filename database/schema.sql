-- ============================================================
--  Bank AI Agent — Schema & Sample Data
--  Run:  mysql -u root -p < database/schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS bank_ai_agent;
USE bank_ai_agent;

-- ────────────────────────────────────────────────────────────
-- TABLES
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    customer_id       VARCHAR(10) UNIQUE NOT NULL,
    first_name        VARCHAR(50) NOT NULL,
    last_name         VARCHAR(50) NOT NULL,
    email             VARCHAR(100) UNIQUE NOT NULL,
    phone             VARCHAR(20),
    date_of_birth     DATE,
    address           TEXT,
    city              VARCHAR(50),
    state             VARCHAR(50),
    zip_code          VARCHAR(10),
    credit_score      INT,
    annual_income     DECIMAL(12,2),
    employment_status ENUM('employed','self_employed','unemployed','retired') DEFAULT 'employed',
    account_type      ENUM('savings','checking','both') DEFAULT 'both',
    account_balance   DECIMAL(12,2) DEFAULT 0.00,
    member_since      DATE,
    kyc_verified      BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loan_products (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    product_code        VARCHAR(20) UNIQUE NOT NULL,
    product_name        VARCHAR(100) NOT NULL,
    loan_type           ENUM('personal','home','auto','business','education') NOT NULL,
    min_amount          DECIMAL(12,2) NOT NULL,
    max_amount          DECIMAL(12,2) NOT NULL,
    min_tenure_months   INT NOT NULL,
    max_tenure_months   INT NOT NULL,
    base_interest_rate  DECIMAL(5,2) NOT NULL,
    processing_fee_pct  DECIMAL(5,2) DEFAULT 1.00,
    min_credit_score    INT DEFAULT 600,
    description         TEXT,
    is_active           BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS loan_applications (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    application_id    VARCHAR(15) UNIQUE NOT NULL,
    customer_id       VARCHAR(10) NOT NULL,
    product_code      VARCHAR(20) NOT NULL,
    requested_amount  DECIMAL(12,2) NOT NULL,
    approved_amount   DECIMAL(12,2),
    tenure_months     INT NOT NULL,
    purpose           TEXT,
    interest_rate     DECIMAL(5,2),
    emi_amount        DECIMAL(12,2),
    status            ENUM('pending','under_review','approved','rejected','disbursed','closed') DEFAULT 'pending',
    rejection_reason  TEXT,
    applied_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at       TIMESTAMP NULL,
    disbursed_at      TIMESTAMP NULL,
    agent_notes       TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (product_code) REFERENCES loan_products(product_code)
);

CREATE TABLE IF NOT EXISTS loan_repayments (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    application_id      VARCHAR(15) NOT NULL,
    emi_number          INT NOT NULL,
    due_date            DATE NOT NULL,
    paid_date           DATE,
    emi_amount          DECIMAL(12,2) NOT NULL,
    paid_amount         DECIMAL(12,2) DEFAULT 0.00,
    principal_component DECIMAL(12,2),
    interest_component  DECIMAL(12,2),
    status              ENUM('pending','paid','overdue','partial') DEFAULT 'pending',
    FOREIGN KEY (application_id) REFERENCES loan_applications(application_id)
);

CREATE TABLE IF NOT EXISTS ai_audit_log (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    session_id     VARCHAR(50),
    action_type    VARCHAR(50),
    entity_type    VARCHAR(50),
    entity_id      VARCHAR(50),
    tool_name      VARCHAR(100),
    tool_input     JSON,
    tool_output    TEXT,
    ai_reasoning   TEXT,
    executed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- LOAN PRODUCTS
-- ────────────────────────────────────────────────────────────

INSERT INTO loan_products VALUES
(1,'PL001','QuickCash Personal Loan','personal',10000,500000,12,60,10.50,1.50,650,'Fast approval personal loan for all your needs',TRUE),
(2,'HL001','DreamHome Housing Loan','home',500000,10000000,60,360,8.25,0.50,700,'Affordable home loans with flexible EMI',TRUE),
(3,'AL001','AutoDrive Car Loan','auto',100000,2000000,12,84,9.00,1.00,620,'Drive your dream car with competitive rates',TRUE),
(4,'BL001','BizGrow Business Loan','business',200000,5000000,24,84,12.00,2.00,680,'Fuel your business growth with tailored financing',TRUE),
(5,'EL001','EduFuture Education Loan','education',50000,2000000,12,120,7.50,0.25,600,'Invest in your future with our education loans',TRUE);

-- ────────────────────────────────────────────────────────────
-- CUSTOMERS  (20 records)
-- ────────────────────────────────────────────────────────────

INSERT INTO customers (customer_id,first_name,last_name,email,phone,date_of_birth,address,city,state,zip_code,credit_score,annual_income,employment_status,account_type,account_balance,member_since,kyc_verified) VALUES
('CUST0001','Aiden','Clarke','aiden.clarke@email.com','+1-555-0101','1985-03-15','123 Maple Street','New York','NY','10001',745,95000.00,'employed','both',48250.75,'2018-06-12',TRUE),
('CUST0002','Sofia','Mendez','sofia.mendez@email.com','+1-555-0102','1990-07-22','456 Oak Avenue','Los Angeles','CA','90001',680,72000.00,'employed','savings',15800.50,'2020-01-08',TRUE),
('CUST0003','Marcus','Johnson','marcus.j@email.com','+1-555-0103','1978-11-30','789 Pine Road','Chicago','IL','60601',810,145000.00,'self_employed','both',132500.00,'2015-03-20',TRUE),
('CUST0004','Priya','Sharma','priya.sharma@email.com','+1-555-0104','1992-04-18','321 Elm Drive','Houston','TX','77001',590,55000.00,'employed','checking',3200.25,'2021-09-14',FALSE),
('CUST0005','Tyler','Bennett','tyler.b@email.com','+1-555-0105','1988-08-05','654 Cedar Lane','Phoenix','AZ','85001',720,88000.00,'employed','both',27650.00,'2019-04-30',TRUE),
('CUST0006','Amara','Osei','amara.osei@email.com','+1-555-0106','1995-12-10','987 Birch Blvd','Philadelphia','PA','19101',660,63000.00,'employed','savings',9400.00,'2022-02-17',TRUE),
('CUST0007','James','Richardson','james.rich@email.com','+1-555-0107','1975-06-28','147 Walnut Way','San Antonio','TX','78201',785,178000.00,'employed','both',215000.50,'2012-11-05',TRUE),
('CUST0008','Lily','Chen','lily.chen@email.com','+1-555-0108','1993-02-14','258 Spruce Street','San Diego','CA','92101',705,79000.00,'employed','both',22100.75,'2020-07-22',TRUE),
('CUST0009','Devon','Washington','devon.w@email.com','+1-555-0109','1982-09-19','369 Aspen Court','Dallas','TX','75201',540,41000.00,'unemployed','checking',1800.00,'2023-01-11',FALSE),
('CUST0010','Nadia','Petrov','nadia.p@email.com','+1-555-0110','1987-05-07','741 Willow Ave','San Jose','CA','95101',760,118000.00,'employed','both',67890.25,'2017-08-16',TRUE),
('CUST0011','Omar','Hassan','omar.hassan@email.com','+1-555-0111','1980-10-23','852 Magnolia Dr','Austin','TX','78701',695,92000.00,'self_employed','both',38450.00,'2019-12-03',TRUE),
('CUST0012','Grace','Kim','grace.kim@email.com','+1-555-0112','1997-01-16','963 Poplar Path','Jacksonville','FL','32201',630,48000.00,'employed','savings',5600.50,'2022-06-28',TRUE),
('CUST0013','Ethan','Mueller','ethan.m@email.com','+1-555-0113','1984-07-31','159 Sycamore St','San Francisco','CA','94101',820,195000.00,'employed','both',298000.00,'2014-04-09',TRUE),
('CUST0014','Isabelle','Fontaine','isabelle.f@email.com','+1-555-0114','1991-11-04','357 Cypress Ave','Columbus','OH','43201',675,67000.00,'employed','checking',12300.00,'2021-03-25',TRUE),
('CUST0015','Raj','Patel','raj.patel@email.com','+1-555-0115','1979-04-12','486 Redwood Blvd','Charlotte','NC','28201',750,105000.00,'self_employed','both',85000.00,'2016-09-18',TRUE),
('CUST0016','Zoe','Williams','zoe.w@email.com','+1-555-0116','1996-08-27','574 Chestnut Rd','Indianapolis','IN','46201',610,44000.00,'employed','savings',4100.25,'2023-05-07',FALSE),
('CUST0017','Miguel','Torres','miguel.t@email.com','+1-555-0117','1986-03-09','682 Hawthorn Lane','Seattle','WA','98101',730,97000.00,'employed','both',53200.75,'2018-10-14',TRUE),
('CUST0018','Aisha','Robinson','aisha.r@email.com','+1-555-0118','1994-06-21','791 Fir Street','Denver','CO','80201',685,71000.00,'employed','checking',18750.00,'2020-11-30',TRUE),
('CUST0019','Nathan','Brooks','nathan.b@email.com','+1-555-0119','1983-12-08','849 Hemlock Ave','Nashville','TN','37201',560,38000.00,'employed','savings',2900.50,'2022-08-19',FALSE),
('CUST0020','Elena','Kowalski','elena.k@email.com','+1-555-0120','1989-09-14','937 Larch Drive','Portland','OR','97201',775,128000.00,'employed','both',94500.00,'2017-02-26',TRUE);

-- ────────────────────────────────────────────────────────────
-- LOAN APPLICATIONS  (20 records, varied statuses)
-- ────────────────────────────────────────────────────────────

INSERT INTO loan_applications (application_id,customer_id,product_code,requested_amount,approved_amount,tenure_months,purpose,interest_rate,emi_amount,status,rejection_reason,applied_at,reviewed_at,disbursed_at,agent_notes) VALUES
('LOAN-2024-0001','CUST0001','PL001',150000,150000,36,'Home renovation',10.50,4875.32,'disbursed',NULL,'2024-01-10 09:15:00','2024-01-12 14:30:00','2024-01-15 10:00:00','Excellent credit profile. Auto-approved.'),
('LOAN-2024-0002','CUST0002','AL001',800000,750000,60,'Purchase new car',9.50,15773.45,'disbursed',NULL,'2024-02-05 11:00:00','2024-02-07 16:00:00','2024-02-10 09:00:00','Reduced amount due to income ratio.'),
('LOAN-2024-0003','CUST0003','HL001',4500000,4500000,240,'Purchase residential property',8.00,37726.57,'disbursed',NULL,'2024-01-20 10:30:00','2024-01-22 13:00:00','2024-01-28 11:00:00','High income, excellent credit. Premium customer.'),
('LOAN-2024-0004','CUST0004','PL001',100000,NULL,24,'Medical expenses',NULL,NULL,'rejected','Credit score 590 below minimum 650. KYC not verified.','2024-03-01 08:45:00','2024-03-02 10:00:00',NULL,'Referred to credit counseling.'),
('LOAN-2024-0005','CUST0005','BL001',500000,500000,48,'Business expansion',11.50,13073.55,'approved',NULL,'2024-03-15 14:00:00','2024-03-18 09:00:00',NULL,'Awaiting disbursement confirmation.'),
('LOAN-2024-0006','CUST0006','EL001',200000,200000,84,'Masters degree abroad',7.50,3078.52,'disbursed',NULL,'2024-02-20 16:30:00','2024-02-22 11:00:00','2024-03-01 09:30:00','Education loan with moratorium.'),
('LOAN-2024-0007','CUST0007','HL001',8000000,8000000,300,'Luxury home purchase',8.25,62434.12,'disbursed',NULL,'2024-01-05 09:00:00','2024-01-07 10:00:00','2024-01-12 09:00:00','VIP customer. Concierge service applied.'),
('LOAN-2024-0008','CUST0008','PL001',200000,200000,48,'Debt consolidation',10.75,5149.48,'under_review',NULL,'2024-04-01 10:00:00',NULL,NULL,'Pending income verification documents.'),
('LOAN-2024-0009','CUST0009','PL001',50000,NULL,12,'Emergency expenses',NULL,NULL,'rejected','Unemployed. Insufficient repayment capacity.','2024-03-25 12:00:00','2024-03-26 09:00:00',NULL,'Suggested applying after employment.'),
('LOAN-2024-0010','CUST0010','AL001',1200000,1200000,72,'Purchase SUV',9.00,21577.76,'approved',NULL,'2024-04-05 11:30:00','2024-04-07 14:00:00',NULL,'Quick approval. Strong financial profile.'),
('LOAN-2024-0011','CUST0011','BL001',1500000,1200000,60,'Working capital for restaurant',12.50,27088.54,'disbursed',NULL,'2024-02-10 09:00:00','2024-02-14 13:00:00','2024-02-18 10:00:00','Adjusted to 80% after business audit.'),
('LOAN-2024-0012','CUST0012','EL001',800000,800000,96,'Medical school tuition',7.75,10838.55,'pending',NULL,'2024-04-10 08:30:00',NULL,NULL,'Documents under initial screening.'),
('LOAN-2024-0013','CUST0013','HL001',9500000,9500000,360,'Investment property',8.10,70546.23,'disbursed',NULL,'2023-11-15 10:00:00','2023-11-17 11:00:00','2023-11-22 09:00:00','High net worth client. Excellent DSCR.'),
('LOAN-2024-0014','CUST0014','AL001',600000,550000,48,'Used car purchase',9.75,13947.88,'approved',NULL,'2024-04-08 13:00:00','2024-04-09 10:30:00',NULL,'Moderate income. Amount adjusted.'),
('LOAN-2024-0015','CUST0015','BL001',3000000,3000000,72,'IT consulting firm expansion',11.75,56852.66,'disbursed',NULL,'2024-01-28 14:00:00','2024-02-02 09:00:00','2024-02-07 10:00:00','Solid business plan. 3 years track record.'),
('LOAN-2024-0016','CUST0016','PL001',80000,NULL,24,'Wedding expenses',NULL,NULL,'rejected','Credit score 610 below minimum 650. Insufficient income docs.','2024-04-02 10:30:00','2024-04-03 11:00:00',NULL,'Suggested secured loan alternative.'),
('LOAN-2024-0017','CUST0017','PL001',300000,300000,36,'Home appliances',10.50,9750.65,'under_review',NULL,'2024-04-09 09:00:00',NULL,NULL,'Awaiting employer verification.'),
('LOAN-2024-0018','CUST0018','AL001',900000,900000,60,'New electric vehicle',8.75,18579.34,'disbursed',NULL,'2024-03-10 11:00:00','2024-03-12 14:00:00','2024-03-16 10:00:00','EV loan — green initiative rate applied.'),
('LOAN-2024-0019','CUST0019','PL001',60000,NULL,18,'Urgent home repair',NULL,NULL,'rejected','Low credit score 560. High debt-to-income ratio.','2024-04-06 15:00:00','2024-04-07 09:30:00',NULL,'Advised to improve credit score first.'),
('LOAN-2024-0020','CUST0020','HL001',5500000,5500000,300,'Second home purchase',8.15,43254.89,'approved',NULL,'2024-04-11 10:00:00','2024-04-12 11:30:00',NULL,'Pre-approved. Waiting for property registration.');

-- ────────────────────────────────────────────────────────────
-- REPAYMENTS  (for disbursed loans)
-- ────────────────────────────────────────────────────────────

INSERT INTO loan_repayments (application_id,emi_number,due_date,paid_date,emi_amount,paid_amount,principal_component,interest_component,status) VALUES
('LOAN-2024-0001',1,'2024-02-15','2024-02-14',4875.32,4875.32,3562.57,1312.75,'paid'),
('LOAN-2024-0001',2,'2024-03-15','2024-03-13',4875.32,4875.32,3593.77,1281.55,'paid'),
('LOAN-2024-0001',3,'2024-04-15',NULL,4875.32,0.00,3625.24,1250.08,'pending'),
('LOAN-2024-0002',1,'2024-03-10','2024-03-09',15773.45,15773.45,9836.20,5937.25,'paid'),
('LOAN-2024-0002',2,'2024-04-10','2024-04-08',15773.45,15773.45,9913.93,5859.52,'paid'),
('LOAN-2024-0003',1,'2024-02-28','2024-02-27',37726.57,37726.57,7726.57,30000.00,'paid'),
('LOAN-2024-0003',2,'2024-03-28','2024-03-25',37726.57,37726.57,7777.97,29948.60,'paid'),
('LOAN-2024-0003',3,'2024-04-28',NULL,37726.57,0.00,7829.82,29896.75,'pending'),
('LOAN-2024-0006',1,'2024-04-01','2024-03-30',3078.52,3078.52,822.77,2255.75,'paid'),
('LOAN-2024-0007',1,'2024-02-12','2024-02-11',62434.12,62434.12,17434.12,45000.00,'paid'),
('LOAN-2024-0007',2,'2024-03-12','2024-03-10',62434.12,62434.12,17554.65,44879.47,'paid'),
('LOAN-2024-0011',1,'2024-03-18','2024-03-17',27088.54,27088.54,11588.54,15500.00,'paid'),
('LOAN-2024-0011',2,'2024-04-18',NULL,27088.54,0.00,11710.86,15377.68,'pending'),
('LOAN-2024-0013',1,'2023-12-22','2023-12-21',70546.23,70546.23,6296.23,64250.00,'paid'),
('LOAN-2024-0013',2,'2024-01-22','2024-01-20',70546.23,70546.23,6339.10,64207.13,'paid'),
('LOAN-2024-0013',3,'2024-02-22','2024-02-19',70546.23,70546.23,6382.26,64163.97,'paid'),
('LOAN-2024-0013',4,'2024-03-22','2024-03-20',70546.23,70546.23,6425.70,64120.53,'paid'),
('LOAN-2024-0013',5,'2024-04-22',NULL,70546.23,0.00,6469.44,64076.79,'pending'),
('LOAN-2024-0015',1,'2024-03-07','2024-03-06',56852.66,56852.66,27352.66,29500.00,'paid'),
('LOAN-2024-0015',2,'2024-04-07','2024-04-05',56852.66,56852.66,27621.55,29231.11,'paid'),
('LOAN-2024-0018',1,'2024-04-16','2024-04-15',18579.34,18579.34,11454.34,7125.00,'paid');

-- ────────────────────────────────────────────────────────────
-- VIEWS
-- ────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_loan_summary AS
SELECT
    la.application_id, la.customer_id,
    CONCAT(c.first_name,' ',c.last_name) AS customer_name,
    lp.product_name, lp.loan_type,
    la.requested_amount, la.approved_amount,
    la.tenure_months, la.interest_rate, la.emi_amount,
    la.status, la.applied_at,
    c.credit_score, c.annual_income, c.employment_status
FROM loan_applications la
JOIN customers c  ON la.customer_id  = c.customer_id
JOIN loan_products lp ON la.product_code = lp.product_code;

CREATE OR REPLACE VIEW v_portfolio_stats AS
SELECT
    COUNT(*)                                               AS total_applications,
    SUM(status='disbursed')                                AS disbursed,
    SUM(status='approved')                                 AS approved,
    SUM(status='under_review')                             AS under_review,
    SUM(status='rejected')                                 AS rejected,
    SUM(status='pending')                                  AS pending,
    SUM(IFNULL(approved_amount,0))                         AS total_approved_amount,
    ROUND(AVG(CASE WHEN status NOT IN ('rejected','pending') THEN interest_rate END),2) AS avg_interest_rate,
    ROUND(AVG(CASE WHEN status NOT IN ('rejected','pending') THEN tenure_months END),1) AS avg_tenure_months
FROM loan_applications;

-- Verify setup
SELECT 'Setup complete' AS status;
SELECT COUNT(*) AS customers        FROM customers;
SELECT COUNT(*) AS loan_products    FROM loan_products;
SELECT COUNT(*) AS loan_applications FROM loan_applications;
SELECT COUNT(*) AS repayment_records FROM loan_repayments;
