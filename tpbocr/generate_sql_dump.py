# -*- coding: utf-8 -*-
"""Generate a standalone, production-ready SQL import dump (tpb_1891_full_import.sql)
for thinkhomeo.in containing table definitions and batch INSERT statements
for rubrics, remedies, links (with bounding boxes), and page manifests.
"""
import os, sys, csv, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(ROOT, "out", "tpb_live_package")
DATA_DIR = os.path.join(PKG_DIR, "data")
SCHEMA_DIR = os.path.join(PKG_DIR, "schema")
OUT_SQL = os.path.join(SCHEMA_DIR, "tpb_1891_full_import.sql")

def escape_sql(val):
    if val is None:
        return "NULL"
    s = str(val).replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"

def main():
    print("=== GENERATING THINKHOMEO.IN PRODUCTION SQL DUMP ===")

    with open(OUT_SQL, "w", encoding="utf-8") as f_out:
        # 1. Header and DDL
        f_out.write("""-- ====================================================================
-- thinkhomeo.in - Boenninghausen/Allen TPB 1891 Bilingual Database Import Dump
-- Tables: rep_rubric, rep_remedy, rep_link, rep_page_manifest, rep_verification_feedback
-- Target: MySQL 8.0+ / MariaDB 10.5+ / PostgreSQL (via MySQL compatibility)
-- Character Set: utf8mb4 / utf8mb4_unicode_ci
-- ====================================================================

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `rep_verification_feedback`;
DROP TABLE IF EXISTS `rep_link`;
DROP TABLE IF EXISTS `rep_rubric`;
DROP TABLE IF EXISTS `rep_remedy`;
DROP TABLE IF EXISTS `rep_page_manifest`;

-- 1. rep_rubric table
CREATE TABLE `rep_rubric` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `path` VARCHAR(255) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `name_hi` VARCHAR(500) NOT NULL,
  `level` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `page_start` INT UNSIGNED NULL,
  `page_end` INT UNSIGNED NULL,
  `token_count` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_rubric_name` (`name`),
  KEY `idx_rubric_level` (`level`),
  FULLTEXT KEY `ft_rubric_bilingual` (`name`, `name_hi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. rep_remedy table
CREATE TABLE `rep_remedy` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `abbrev` VARCHAR(32) NOT NULL,
  `norm` VARCHAR(32) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `name_hi` VARCHAR(128) NOT NULL,
  `standard_abbrev` VARCHAR(32) NOT NULL,
  `common_name` VARCHAR(128) NULL,
  `common_name_hi` VARCHAR(128) NULL,
  `name_source` VARCHAR(32) NOT NULL DEFAULT 'core125(PD)',
  `occurrences` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_remedy_norm` (`norm`),
  KEY `idx_remedy_std_abbrev` (`standard_abbrev`),
  FULLTEXT KEY `ft_remedy_names` (`name`, `name_hi`, `abbrev`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. rep_link table
CREATE TABLE `rep_link` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `rubric_id` INT UNSIGNED NOT NULL,
  `remedy_id` INT UNSIGNED NOT NULL,
  `grade` TINYINT UNSIGNED NOT NULL,
  `grade_name` VARCHAR(16) NOT NULL,
  `page` SMALLINT UNSIGNED NOT NULL,
  `bbox_pixel` JSON NOT NULL,
  `bbox_pct` JSON NOT NULL,
  `provenance` VARCHAR(64) NULL,
  PRIMARY KEY (`id`),
  KEY `idx_link_rubric_grade` (`rubric_id`, `grade`),
  KEY `idx_link_remedy_grade` (`remedy_id`, `grade`),
  KEY `idx_link_page` (`page`),
  CONSTRAINT `fk_rep_link_rubric` FOREIGN KEY (`rubric_id`) REFERENCES `rep_rubric` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_rep_link_remedy` FOREIGN KEY (`remedy_id`) REFERENCES `rep_remedy` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. rep_page_manifest table
CREATE TABLE `rep_page_manifest` (
  `book_page` SMALLINT UNSIGNED NOT NULL,
  `leaf_number` SMALLINT UNSIGNED NOT NULL,
  `image_filename` VARCHAR(64) NOT NULL,
  `canvas_width` SMALLINT UNSIGNED NOT NULL DEFAULT 2600,
  `canvas_height` SMALLINT UNSIGNED NOT NULL DEFAULT 4242,
  `token_count` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`book_page`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. rep_verification_feedback table
CREATE TABLE `rep_verification_feedback` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `link_id` BIGINT UNSIGNED NOT NULL,
  `user_id` BIGINT UNSIGNED NULL,
  `action` ENUM('confirmed', 'discrepancy_reported') NOT NULL,
  `suggested_grade` TINYINT UNSIGNED NULL,
  `user_comment` TEXT NULL,
  `user_ip` VARCHAR(45) NULL,
  `status` ENUM('pending', 'verified', 'rejected') NOT NULL DEFAULT 'pending',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_feedback_link` (`link_id`),
  KEY `idx_feedback_status` (`status`),
  CONSTRAINT `fk_feedback_link` FOREIGN KEY (`link_id`) REFERENCES `rep_link` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

""")

        # 2. Insert rep_rubric
        print("Writing rep_rubric INSERT statements...")
        with open(os.path.join(DATA_DIR, "rep_rubric.csv"), encoding="utf-8-sig") as f:
            rubs = list(csv.DictReader(f))

        f_out.write("\n-- INSERTING 1,676 RUBRICS\n")
        f_out.write("INSERT INTO `rep_rubric` (`id`, `path`, `name`, `name_hi`, `level`, `page_start`, `page_end`, `token_count`) VALUES\n")
        rub_lines = []
        for r in rubs:
            p_start = r["page_start"] if r["page_start"] else "NULL"
            p_end = r["page_end"] if r["page_end"] else "NULL"
            rub_lines.append(f"({r['id']}, {escape_sql(r['path'])}, {escape_sql(r['name'])}, {escape_sql(r['name_hi'])}, {r['level']}, {p_start}, {p_end}, {r.get('token_count', 0)})")
        f_out.write(",\n".join(rub_lines) + ";\n")

        # 3. Insert rep_remedy
        print("Writing rep_remedy INSERT statements...")
        with open(os.path.join(DATA_DIR, "rep_remedy.csv"), encoding="utf-8-sig") as f:
            rems = list(csv.DictReader(f))

        f_out.write("\n-- INSERTING 605 REMEDIES\n")
        f_out.write("INSERT INTO `rep_remedy` (`id`, `abbrev`, `norm`, `name`, `name_hi`, `standard_abbrev`, `common_name`, `common_name_hi`, `name_source`, `occurrences`) VALUES\n")
        rem_lines = []
        for r in rems:
            rem_lines.append(f"({r['id']}, {escape_sql(r['abbrev'])}, {escape_sql(r['norm'])}, {escape_sql(r['name'])}, {escape_sql(r['name_hi'])}, {escape_sql(r['standard_abbrev'])}, {escape_sql(r.get('common_name',''))}, {escape_sql(r.get('common_name_hi',''))}, {escape_sql(r.get('name_source','core125(PD)'))}, {r.get('occurrences',0)})")
        f_out.write(",\n".join(rem_lines) + ";\n")

        # 4. Insert rep_page_manifest
        print("Writing rep_page_manifest INSERT statements...")
        manifest = json.load(open(os.path.join(DATA_DIR, "page_manifest.json"), encoding="utf-8"))["pages"]
        f_out.write("\n-- INSERTING 466 PAGE MANIFEST RECORDS\n")
        f_out.write("INSERT INTO `rep_page_manifest` (`book_page`, `leaf_number`, `image_filename`, `canvas_width`, `canvas_height`, `token_count`) VALUES\n")
        man_lines = []
        for m in manifest:
            man_lines.append(f"({m['book_page']}, {m['leaf_number']}, {escape_sql(m['image_filename'])}, {m['canvas_width']}, {m['canvas_height']}, {m['token_count']})")
        f_out.write(",\n".join(man_lines) + ";\n")

        # 5. Insert rep_link in chunks of 1000
        print("Writing rep_link INSERT statements (132,367 rows in batches of 1,000)...")
        with open(os.path.join(DATA_DIR, "tpb_final_graded.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        # We need rubric_id and remedy_id mapping
        rub_id_map = {r["name"]: r["id"] for r in rubs}
        rem_id_map = {r["norm"]: r["id"] for r in rems}

        f_out.write("\n-- INSERTING 132,367 GRADED REPERTORY LINKS WITH BOUNDING BOXES\n")
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            link_lines = []
            for idx_in_chunk, r in enumerate(chunk):
                link_id = i + idx_in_chunk + 1
                rub_id = rub_id_map.get(r["rubric"], 1)
                rem_id = rem_id_map.get(r["norm_remedy"], 1)
                bbox_px = r.get("bbox", "[]")
                bbox_pct = r.get("bbox_pct", "[]")
                prov = r.get("provenance", "")
                link_lines.append(f"({link_id}, {rub_id}, {rem_id}, {r['grade']}, {escape_sql(r['grade_name'])}, {r['page']}, {escape_sql(bbox_px)}, {escape_sql(bbox_pct)}, {escape_sql(prov)})")

            f_out.write("INSERT INTO `rep_link` (`id`, `rubric_id`, `remedy_id`, `grade`, `grade_name`, `page`, `bbox_pixel`, `bbox_pct`, `provenance`) VALUES\n")
            f_out.write(",\n".join(link_lines) + ";\n")

        # Enable foreign keys
        f_out.write("\nSET FOREIGN_KEY_CHECKS = 1;\n-- IMPORT COMPLETED SUCCESSFULLY!\n")

    sz_mb = os.path.getsize(OUT_SQL) / (1024 * 1024)
    print(f"SUCCESS: Generated {OUT_SQL} ({sz_mb:.2f} MB)")

if __name__ == "__main__":
    main()
