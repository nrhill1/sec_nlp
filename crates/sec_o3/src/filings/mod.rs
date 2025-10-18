//! SEC filing form types and metadata.
//!
//! This module provides the [`FormType`] enum which represents all SEC filing types,
//! along with helper functions for parsing and working with form types.
use std::fmt;
use std::str::FromStr;

use crate::Error;

/// SEC filing form types.
///
/// This enum represents all major SEC filing form types including:
/// - Periodic reports (10-K, 10-Q)
/// - Current reports (8-K)
/// - Proxy statements (DEF 14A, etc.)
/// - Registration statements (S-1, S-3, etc.)
/// - Foreign issuer forms (20-F, 6-K, etc.)
/// - Insider trading forms (3, 4, 5)
/// - And many others
#[allow(clippy::enum_variant_names)]
#[rustfmt::skip]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FormType {
    // Periodic Reports
    /// Annual report (10-K)
    TenK,
    /// Amended annual report (10-K/A)
    TenKA,
    /// Quarterly report (10-Q)
    TenQ,
    /// Amended quarterly report (10-Q/A)
    TenQA,

    // Current Reports
    /// Current report (8-K)
    EightK,
    /// Amended current report (8-K/A)
    EightKA,

    // Proxy Statements
    /// Definitive proxy statement
    Def14A,
    /// Definitive consent solicitation
    Def14C,
    /// Definitive merger proxy
    DefM14A,
    /// Amended definitive merger proxy
    DefM14AA,
    /// Definitive contested proxy
    DefC14A,
    /// Amended definitive contested proxy
    DefC14AA,
    /// Definitive contested consent
    DefC14C,
    /// Amended definitive contested consent
    DefC14CA,

    // Registration Statements - S Series
    /// IPO registration statement
    S1,
    /// Amended S-1
    S1A,
    /// Shelf registration for existing public companies
    S3,
    /// Amended S-3
    S3A,
    /// Business combination registration
    S4,
    /// Amended S-4
    S4A,
    /// Employee benefit plan securities
    S8,
    /// Amended S-8
    S8A,
    /// REIT registration
    S11,
    /// Amended S-11
    S11A,

    // Small Business Forms
    /// Small business registration
    SB1,
    /// Small business registration
    SB2,
    /// Amended SB-1
    SB1A,
    /// Amended SB-2
    SB2A,

    // Foreign Private Issuers
    /// Annual report for foreign issuers
    TwentyF,
    /// Amended 20-F
    TwentyFA,
    /// Current report for foreign issuers
    SixK,
    /// Amended 6-K
    SixKA,
    /// Canadian annual report
    FortyF,
    /// Amended 40-F
    FortyFA,
    /// Registration of Canadian securities
    FortyFR12B,
    /// Amended 40-FR12B
    FortyFR12BA,
    /// Registration termination for Canadian securities
    FortyFR12G,
    /// Amended 40-FR12G
    FortyFR12GA,

    // Foreign Registration - F Series
    /// Foreign IPO registration
    F1,
    /// Amended F-1
    F1A,
    /// Foreign shelf registration
    F3,
    /// Foreign delayed shelf
    F3D,
    /// Foreign business combination
    F4,
    /// Foreign business combination (effective)
    F4EF,
    /// Foreign depository receipts
    F6,
    /// Foreign depository receipts (effective)
    F6EF,

    // Employee Benefit Plans
    /// Employee benefit plan annual report
    ElevenK,
    /// Amended 11-K
    ElevenKA,

    // Institutional Investment Managers
    /// Institutional holdings report
    ThirteenFHr,
    /// Amended 13F-HR
    ThirteenFHrA,
    /// Institutional holdings notice
    ThirteenFNT,
    /// Amended 13F-NT
    ThirteenFNTA,

    // Beneficial Ownership
    /// 5%+ ownership report
    Sc13D,
    /// Amended SC 13D
    Sc13DA,
    /// Passive investor 5%+ ownership
    Sc13G,
    /// Amended SC 13G
    Sc13GA,

    // Insider Trading
    /// Initial insider ownership
    Form3,
    /// Amended Form 3
    Form3A,
    /// Change in insider ownership
    Form4,
    /// Amended Form 4
    Form4A,
    /// Annual insider ownership
    Form5,
    /// Amended Form 5
    Form5A,

    // Offerings & Prospectuses
    /// Prospectus filed under 424(b)(5)
    FourTwoFourB5,
    /// Merger prospectus
    FourTwoFive,
    /// Post-effective amendment
    PosEx,
    /// Post-effective under 462(b)
    Pos462B,
    /// Post-effective under 462(c)
    Pos462C,
    /// Automatic shelf registration post-effective
    PosAsr,

    // Exempt Offerings
    /// Sale of restricted securities
    OneFortyFour,
    /// Amended 144
    OneFortyFourA,
    /// Exempt offering
    FormD,

    // Notifications
    /// Late 10-K notification
    NT10K,
    /// Amended NT 10-K
    NT10KA,
    /// Late 10-Q notification
    NT10Q,
    /// Amended NT 10-Q
    NT10QA,
    /// Late 11-K notification
    NT11K,
    /// Late foreign issuer notification
    NT15D2,

    // Other
    /// Investment company filing
    TwentyFive,
    /// Amended 25
    TwentyFiveA,
    /// Registration withdrawal
    Rw,
    /// Registration withdrawal request
    RwWd,
}

impl fmt::Display for FormType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            // Periodic Reports
            FormType::TenK => "10-K",
            FormType::TenKA => "10-K/A",
            FormType::TenQ => "10-Q",
            FormType::TenQA => "10-Q/A",

            // Current Reports
            FormType::EightK => "8-K",
            FormType::EightKA => "8-K/A",

            // Proxy Statements
            FormType::Def14A => "DEF 14A",
            FormType::Def14C => "DEF 14C",
            FormType::DefM14A => "DEFM14A",
            FormType::DefM14AA => "DEFM14A/A",
            FormType::DefC14A => "DEFC14A",
            FormType::DefC14AA => "DEFC14A/A",
            FormType::DefC14C => "DEFC14C",
            FormType::DefC14CA => "DEFC14C/A",

            // Registration Statements - S Series
            FormType::S1 => "S-1",
            FormType::S1A => "S-1/A",
            FormType::S3 => "S-3",
            FormType::S3A => "S-3/A",
            FormType::S4 => "S-4",
            FormType::S4A => "S-4/A",
            FormType::S8 => "S-8",
            FormType::S8A => "S-8/A",
            FormType::S11 => "S-11",
            FormType::S11A => "S-11/A",

            // Small Business Forms
            FormType::SB1 => "SB-1",
            FormType::SB2 => "SB-2",
            FormType::SB1A => "SB-1/A",
            FormType::SB2A => "SB-2/A",

            // Foreign Private Issuers
            FormType::TwentyF => "20-F",
            FormType::TwentyFA => "20-F/A",
            FormType::SixK => "6-K",
            FormType::SixKA => "6-K/A",
            FormType::FortyF => "40-F",
            FormType::FortyFA => "40-F/A",
            FormType::FortyFR12B => "40-FR12B",
            FormType::FortyFR12BA => "40-FR12B/A",
            FormType::FortyFR12G => "40-FR12G",
            FormType::FortyFR12GA => "40-FR12G/A",

            // Foreign Registration - F Series
            FormType::F1 => "F-1",
            FormType::F1A => "F-1/A",
            FormType::F3 => "F-3",
            FormType::F3D => "F-3D",
            FormType::F4 => "F-4",
            FormType::F4EF => "F-4EF",
            FormType::F6 => "F-6",
            FormType::F6EF => "F-6EF",

            // Employee Benefit Plans
            FormType::ElevenK => "11-K",
            FormType::ElevenKA => "11-K/A",

            // Institutional Investment Managers
            FormType::ThirteenFHr => "13F-HR",
            FormType::ThirteenFHrA => "13F-HR/A",
            FormType::ThirteenFNT => "13F-NT",
            FormType::ThirteenFNTA => "13F-NT/A",

            // Beneficial Ownership
            FormType::Sc13D => "SC 13D",
            FormType::Sc13DA => "SC 13D/A",
            FormType::Sc13G => "SC 13G",
            FormType::Sc13GA => "SC 13G/A",

            // Insider Trading
            FormType::Form3 => "3",
            FormType::Form3A => "3/A",
            FormType::Form4 => "4",
            FormType::Form4A => "4/A",
            FormType::Form5 => "5",
            FormType::Form5A => "5/A",

            // Offerings & Prospectuses
            FormType::FourTwoFourB5 => "424B5",
            FormType::FourTwoFive => "425",
            FormType::PosEx => "POS EX",
            FormType::Pos462B => "POS 462B",
            FormType::Pos462C => "POS 462C",
            FormType::PosAsr => "POS ASR",

            // Exempt Offerings
            FormType::OneFortyFour => "144",
            FormType::OneFortyFourA => "144/A",
            FormType::FormD => "D",

            // Notifications
            FormType::NT10K => "NT 10-K",
            FormType::NT10KA => "NT 10-K/A",
            FormType::NT10Q => "NT 10-Q",
            FormType::NT10QA => "NT 10-Q/A",
            FormType::NT11K => "NT 11-K",
            FormType::NT15D2 => "NT 15D2",

            // Other
            FormType::TwentyFive => "25",
            FormType::TwentyFiveA => "25/A",
            FormType::Rw => "RW",
            FormType::RwWd => "RW/Wd",
        };
        write!(f, "{}", s)
    }
}

impl FromStr for FormType {
    type Err = Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let up = s.trim().to_uppercase();
        match up.as_str() {
            "10-K" | "10K" => Ok(FormType::TenK),
            "10-K/A" | "10K/A" => Ok(FormType::TenKA),
            "10-Q" | "10Q" => Ok(FormType::TenQ),
            "10-Q/A" | "10Q/A" => Ok(FormType::TenQA),
            "8-K" | "8K" => Ok(FormType::EightK),
            "8-K/A" | "8K/A" => Ok(FormType::EightKA),
            "DEF 14A" | "DEF14A" => Ok(FormType::Def14A),
            "DEF 14C" | "DEF14C" => Ok(FormType::Def14C),
            "S-1" | "S1" => Ok(FormType::S1),
            "S-1/A" | "S1/A" => Ok(FormType::S1A),
            "S-3" | "S3" => Ok(FormType::S3),
            "S-3/A" | "S3/A" => Ok(FormType::S3A),
            "S-4" | "S4" => Ok(FormType::S4),
            "S-4/A" | "S4/A" => Ok(FormType::S4A),
            "S-8" | "S8" => Ok(FormType::S8),
            "S-8/A" | "S8/A" => Ok(FormType::S8A),
            "20-F" | "20F" => Ok(FormType::TwentyF),
            "20-F/A" | "20F/A" => Ok(FormType::TwentyFA),
            "6-K" | "6K" => Ok(FormType::SixK),
            "6-K/A" | "6K/A" => Ok(FormType::SixKA),
            "11-K" | "11K" => Ok(FormType::ElevenK),
            "11-K/A" | "11K/A" => Ok(FormType::ElevenKA),
            "13F-HR" | "13FHR" => Ok(FormType::ThirteenFHr),
            "13F-HR/A" | "13FHR/A" => Ok(FormType::ThirteenFHrA),
            "13F-NT" => Ok(FormType::ThirteenFNT),
            "13F-NT/A" => Ok(FormType::ThirteenFNTA),
            "144" => Ok(FormType::OneFortyFour),
            "144/A" => Ok(FormType::OneFortyFourA),
            "SC 13D" | "SC13D" => Ok(FormType::Sc13D),
            "SC 13D/A" | "SC13D/A" => Ok(FormType::Sc13DA),
            "SC 13G" | "SC13G" => Ok(FormType::Sc13G),
            "SC 13G/A" | "SC13G/A" => Ok(FormType::Sc13GA),
            "3" => Ok(FormType::Form3),
            "3/A" => Ok(FormType::Form3A),
            "4" => Ok(FormType::Form4),
            "4/A" => Ok(FormType::Form4A),
            "5" => Ok(FormType::Form5),
            "5/A" => Ok(FormType::Form5A),
            "424B5" => Ok(FormType::FourTwoFourB5),
            "425" => Ok(FormType::FourTwoFive),
            "F-1" | "F1" => Ok(FormType::F1),
            "F-1/A" | "F1/A" => Ok(FormType::F1A),
            "F-3" | "F3" => Ok(FormType::F3),
            "F-3D" | "F3D" => Ok(FormType::F3D),
            "F-4" | "F4" => Ok(FormType::F4),
            "F-4EF" | "F4EF" => Ok(FormType::F4EF),
            "F-6" | "F6" => Ok(FormType::F6),
            "F-6EF" | "F6EF" => Ok(FormType::F6EF),
            "S-11" | "S11" => Ok(FormType::S11),
            "S-11/A" | "S11/A" => Ok(FormType::S11A),
            "SB-1" | "SB1" => Ok(FormType::SB1),
            "SB-2" | "SB2" => Ok(FormType::SB2),
            "SB-1/A" | "SB1/A" => Ok(FormType::SB1A),
            "SB-2/A" | "SB2/A" => Ok(FormType::SB2A),
            "D" => Ok(FormType::FormD),
            "DEFM14A" => Ok(FormType::DefM14A),
            "DEFM14A/A" | "DEFM14AA" => Ok(FormType::DefM14AA),
            "DEFC14A" => Ok(FormType::DefC14A),
            "DEFC14A/A" | "DEFC14AA" => Ok(FormType::DefC14AA),
            "DEFC14C" => Ok(FormType::DefC14C),
            "DEFC14C/A" | "DEFC14CA" => Ok(FormType::DefC14CA),
            "40-F" | "40F" => Ok(FormType::FortyF),
            "40-F/A" | "40F/A" => Ok(FormType::FortyFA),
            "40-FR12B" | "40FR12B" => Ok(FormType::FortyFR12B),
            "40-FR12B/A" | "40FR12BA" => Ok(FormType::FortyFR12BA),
            "40-FR12G" | "40FR12G" => Ok(FormType::FortyFR12G),
            "40-FR12G/A" | "40FR12GA" => Ok(FormType::FortyFR12GA),
            "POS EX" => Ok(FormType::PosEx),
            "POS 462B" => Ok(FormType::Pos462B),
            "POS 462C" => Ok(FormType::Pos462C),
            "POS ASR" => Ok(FormType::PosAsr),
            "NT 10-K" => Ok(FormType::NT10K),
            "NT 10-K/A" | "NT10KA" => Ok(FormType::NT10KA),
            "NT 10-Q" => Ok(FormType::NT10Q),
            "NT 10-Q/A" | "NT10QA" => Ok(FormType::NT10QA),
            "NT 11-K" | "NT11K" => Ok(FormType::NT11K),
            "NT15D2" => Ok(FormType::NT15D2),
            "25" => Ok(FormType::TwentyFive),
            "25/A" => Ok(FormType::TwentyFiveA),
            "RW" => Ok(FormType::Rw),
            "RW/WD" | "RW/Wd" => Ok(FormType::RwWd),
            _ => Err(Error::NotFound(format!("unknown form type: {}", s))),
        }
    }
}

/// Check if a string is a valid SEC filing type.
///
/// # Arguments
///
/// * `s` - The string to check
///
/// # Examples
///
/// ```
/// use sec_o3::is_valid_filing_type;
///
/// assert!(is_valid_filing_type("10-K"));
/// assert!(is_valid_filing_type("8-K"));
/// assert!(!is_valid_filing_type("INVALID"));
/// ```
pub fn is_valid_filing_type(s: &str) -> bool {
    FormType::from_str(s).is_ok()
}

/// Filing category classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FilingCategory {
    /// Periodic reports (10-K, 10-Q, etc.)
    PeriodicReport,
    /// Current reports (8-K, 6-K)
    CurrentReport,
    /// Proxy statements
    ProxyStatement,
    /// Registration statements
    Registration,
    /// Beneficial ownership reports
    BeneficialOwnership,
    /// Insider trading reports
    InsiderTrading,
    /// Institutional holdings reports
    InstitutionalHoldings,
    /// Foreign issuer filings
    ForeignIssuer,
    /// Securities offering documents
    Offering,
    /// Late filing notifications
    Notification,
    /// Other filing types
    Other,
}

/// Filing frequency classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FilingFrequency {
    /// Filed annually
    Annual,
    /// Filed quarterly
    Quarterly,
    /// Filed semi-annually
    SemiAnnual,
    /// Filed when events occur
    EventDriven,
    /// Filed continuously
    Ongoing,
    /// Filed as needed
    AsNeeded,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_and_from_str_roundtrip() {
        for &s in &[
            "10-K",
            "10-K/A",
            "8-K",
            "8-K/A",
            "DEF 14A",
            "S-3/A",
            "144/A",
            "SC 13D/A",
            "DEFM14A/A",
            "40-F/A",
            "25/A",
            "RW/Wd",
        ] {
            let f = FormType::from_str(s).expect(&format!("from_str failed for {}", s));
            let out = f.to_string();
            assert_eq!(out, s);
        }
    }
}
