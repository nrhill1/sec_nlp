// ============================================================================
// src/filings/mod.rs - SEC Form Type enum
// ============================================================================
use std::fmt;
use std::str::FromStr;

use crate::errors::ValidationError;

#[allow(clippy::enum_variant_names)]
#[rustfmt::skip]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SecFormType {
    // Periodic Reports
    TenK, TenKA, TenQ, TenQA,

    // Current Reports
    EightK, EightKA,

    // Proxy Statements
    Def14A, Def14C, DefM14A, DefM14AA, DefC14A, DefC14AA, DefC14C, DefC14CA,

    // Registration Statements - S Series
    S1, S1A, S3, S3A, S4, S4A, S8, S8A, S11, S11A,

    // Small Business Forms
    SB1, SB2, SB1A, SB2A,

    // Foreign Private Issuers
    TwentyF, TwentyFA, SixK, SixKA, FortyF, FortyFA,
    FortyFR12B, FortyFR12BA, FortyFR12G, FortyFR12GA,

    // Foreign Registration - F Series
    F1, F1A, F3, F3D, F4, F4EF, F6, F6EF,

    // Employee Benefit Plans
    ElevenK, ElevenKA,

    // Institutional Investment Managers
    ThirteenFHr, ThirteenFHrA, ThirteenFNT, ThirteenFNTA,

    // Beneficial Ownership
    Sc13D, Sc13DA, Sc13G, Sc13GA,

    // Insider Trading
    Form3, Form3A, Form4, Form4A, Form5, Form5A,

    // Offerings & Prospectuses
    FourTwoFourB5, FourTwoFive, PosEx, Pos462B, Pos462C, PosAsr,

    // Exempt Offerings
    OneFortyFour, OneFortyFourA, FormD,

    // Notifications
    NT10K, NT10KA, NT10Q, NT10QA, NT11K, NT15D2,

    // Other
    TwentyFive, TwentyFiveA, Rw, RwWd,
}

// impl SecFormType {
//     /// Returns true if this is an amended filing
//     pub fn is_amendment(&self) -> bool { /* ... */ }

//     /// Returns the base form type (strips /A)
//     pub fn base_type(&self) -> Self { /* ... */ }

//     /// Returns the filing category
//     pub fn category(&self) -> FilingCategory { /* ... */ }

//     /// Returns typical filing frequency
//     pub fn frequency(&self) -> FilingFrequency { /* ... */ }
// }

impl fmt::Display for SecFormType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            // Periodic Reports
            SecFormType::TenK => "10-K",
            SecFormType::TenKA => "10-K/A",
            SecFormType::TenQ => "10-Q",
            SecFormType::TenQA => "10-Q/A",

            // Current Reports
            SecFormType::EightK => "8-K",
            SecFormType::EightKA => "8-K/A",

            // Proxy Statements
            SecFormType::Def14A => "DEF 14A",
            SecFormType::Def14C => "DEF 14C",
            SecFormType::DefM14A => "DEFM14A",
            SecFormType::DefM14AA => "DEFM14A/A",
            SecFormType::DefC14A => "DEFC14A",
            SecFormType::DefC14AA => "DEFC14A/A",
            SecFormType::DefC14C => "DEFC14C",
            SecFormType::DefC14CA => "DEFC14C/A",

            // Registration Statements - S Series
            SecFormType::S1 => "S-1",
            SecFormType::S1A => "S-1/A",
            SecFormType::S3 => "S-3",
            SecFormType::S3A => "S-3/A",
            SecFormType::S4 => "S-4",
            SecFormType::S4A => "S-4/A",
            SecFormType::S8 => "S-8",
            SecFormType::S8A => "S-8/A",
            SecFormType::S11 => "S-11",
            SecFormType::S11A => "S-11/A",

            // Small Business Forms
            SecFormType::SB1 => "SB-1",
            SecFormType::SB2 => "SB-2",
            SecFormType::SB1A => "SB-1/A",
            SecFormType::SB2A => "SB-2/A",

            // Foreign Private Issuers
            SecFormType::TwentyF => "20-F",
            SecFormType::TwentyFA => "20-F/A",
            SecFormType::SixK => "6-K",
            SecFormType::SixKA => "6-K/A",
            SecFormType::FortyF => "40-F",
            SecFormType::FortyFA => "40-F/A",
            SecFormType::FortyFR12B => "40-FR12B",
            SecFormType::FortyFR12BA => "40-FR12B/A",
            SecFormType::FortyFR12G => "40-FR12G",
            SecFormType::FortyFR12GA => "40-FR12G/A",

            // Foreign Registration - F Series
            SecFormType::F1 => "F-1",
            SecFormType::F1A => "F-1/A",
            SecFormType::F3 => "F-3",
            SecFormType::F3D => "F-3D",
            SecFormType::F4 => "F-4",
            SecFormType::F4EF => "F-4EF",
            SecFormType::F6 => "F-6",
            SecFormType::F6EF => "F-6EF",

            // Employee Benefit Plans
            SecFormType::ElevenK => "11-K",
            SecFormType::ElevenKA => "11-K/A",

            // Institutional Investment Managers
            SecFormType::ThirteenFHr => "13F-HR",
            SecFormType::ThirteenFHrA => "13F-HR/A",
            SecFormType::ThirteenFNT => "13F-NT",
            SecFormType::ThirteenFNTA => "13F-NT/A",

            // Beneficial Ownership
            SecFormType::Sc13D => "SC 13D",
            SecFormType::Sc13DA => "SC 13D/A",
            SecFormType::Sc13G => "SC 13G",
            SecFormType::Sc13GA => "SC 13G/A",

            // Insider Trading
            SecFormType::Form3 => "3",
            SecFormType::Form3A => "3/A",
            SecFormType::Form4 => "4",
            SecFormType::Form4A => "4/A",
            SecFormType::Form5 => "5",
            SecFormType::Form5A => "5/A",

            // Offerings & Prospectuses
            SecFormType::FourTwoFourB5 => "424B5",
            SecFormType::FourTwoFive => "425",
            SecFormType::PosEx => "POS EX",
            SecFormType::Pos462B => "POS 462B",
            SecFormType::Pos462C => "POS 462C",
            SecFormType::PosAsr => "POS ASR",

            // Exempt Offerings
            SecFormType::OneFortyFour => "144",
            SecFormType::OneFortyFourA => "144/A",
            SecFormType::FormD => "D",

            // Notifications
            SecFormType::NT10K => "NT 10-K",
            SecFormType::NT10KA => "NT 10-K/A",
            SecFormType::NT10Q => "NT 10-Q",
            SecFormType::NT10QA => "NT 10-Q/A",
            SecFormType::NT11K => "NT 11-K",
            SecFormType::NT15D2 => "NT 15D2",

            // Other
            SecFormType::TwentyFive => "25",
            SecFormType::TwentyFiveA => "25/A",
            SecFormType::Rw => "RW",
            SecFormType::RwWd => "RW/Wd",
        };
        write!(f, "{}", s)
    }
}

impl FromStr for SecFormType {
    type Err = ValidationError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let up = s.trim().to_uppercase();
        match up.as_str() {
            "10-K" | "10K" => Ok(SecFormType::TenK),
            "10-K/A" | "10K/A" => Ok(SecFormType::TenKA),
            "10-Q" | "10Q" => Ok(SecFormType::TenQ),
            "10-Q/A" | "10Q/A" => Ok(SecFormType::TenQA),
            "8-K" | "8K" => Ok(SecFormType::EightK),
            "8-K/A" | "8K/A" => Ok(SecFormType::EightKA),
            "DEF 14A" | "DEF14A" => Ok(SecFormType::Def14A),
            "DEF 14C" | "DEF14C" => Ok(SecFormType::Def14C),
            "S-1" | "S1" => Ok(SecFormType::S1),
            "S-1/A" | "S1/A" => Ok(SecFormType::S1A),
            "S-3" | "S3" => Ok(SecFormType::S3),
            "S-3/A" | "S3/A" => Ok(SecFormType::S3A),
            "S-4" | "S4" => Ok(SecFormType::S4),
            "S-4/A" | "S4/A" => Ok(SecFormType::S4A),
            "S-8" | "S8" => Ok(SecFormType::S8),
            "S-8/A" | "S8/A" => Ok(SecFormType::S8A),
            "20-F" | "20F" => Ok(SecFormType::TwentyF),
            "20-F/A" | "20F/A" => Ok(SecFormType::TwentyFA),
            "6-K" | "6K" => Ok(SecFormType::SixK),
            "6-K/A" | "6K/A" => Ok(SecFormType::SixKA),
            "11-K" | "11K" => Ok(SecFormType::ElevenK),
            "11-K/A" | "11K/A" => Ok(SecFormType::ElevenKA),
            "13F-HR" | "13FHR" => Ok(SecFormType::ThirteenFHr),
            "13F-HR/A" | "13FHR/A" => Ok(SecFormType::ThirteenFHrA),
            "13F-NT" => Ok(SecFormType::ThirteenFNT),
            "13F-NT/A" => Ok(SecFormType::ThirteenFNTA),
            "144" => Ok(SecFormType::OneFortyFour),
            "144/A" => Ok(SecFormType::OneFortyFourA),
            "SC 13D" | "SC13D" => Ok(SecFormType::Sc13D),
            "SC 13D/A" | "SC13D/A" => Ok(SecFormType::Sc13DA),
            "SC 13G" | "SC13G" => Ok(SecFormType::Sc13G),
            "SC 13G/A" | "SC13G/A" => Ok(SecFormType::Sc13GA),
            "3" => Ok(SecFormType::Form3),
            "3/A" => Ok(SecFormType::Form3A),
            "4" => Ok(SecFormType::Form4),
            "4/A" => Ok(SecFormType::Form4A),
            "5" => Ok(SecFormType::Form5),
            "5/A" => Ok(SecFormType::Form5A),
            "424B5" => Ok(SecFormType::FourTwoFourB5),
            "425" => Ok(SecFormType::FourTwoFive),
            "F-1" | "F1" => Ok(SecFormType::F1),
            "F-1/A" | "F1/A" => Ok(SecFormType::F1A),
            "F-3" | "F3" => Ok(SecFormType::F3),
            "F-3D" | "F3D" => Ok(SecFormType::F3D),
            "F-4" | "F4" => Ok(SecFormType::F4),
            "F-4EF" | "F4EF" => Ok(SecFormType::F4EF),
            "F-6" | "F6" => Ok(SecFormType::F6),
            "F-6EF" | "F6EF" => Ok(SecFormType::F6EF),
            "S-11" | "S11" => Ok(SecFormType::S11),
            "S-11/A" | "S11/A" => Ok(SecFormType::S11A),
            "SB-1" | "SB1" => Ok(SecFormType::SB1),
            "SB-2" | "SB2" => Ok(SecFormType::SB2),
            "SB-1/A" | "SB1/A" => Ok(SecFormType::SB1A),
            "SB-2/A" | "SB2/A" => Ok(SecFormType::SB2A),
            "D" => Ok(SecFormType::FormD),
            "DEFM14A" => Ok(SecFormType::DefM14A),
            "DEFM14A/A" | "DEFM14AA" => Ok(SecFormType::DefM14AA),
            "DEFC14A" => Ok(SecFormType::DefC14A),
            "DEFC14A/A" | "DEFC14AA" => Ok(SecFormType::DefC14AA),
            "DEFC14C" => Ok(SecFormType::DefC14C),
            "DEFC14C/A" | "DEFC14CA" => Ok(SecFormType::DefC14CA),
            "40-F" | "40F" => Ok(SecFormType::FortyF),
            "40-F/A" | "40F/A" => Ok(SecFormType::FortyFA),
            "40-FR12B" | "40FR12B" => Ok(SecFormType::FortyFR12B),
            "40-FR12B/A" | "40FR12BA" => Ok(SecFormType::FortyFR12BA),
            "40-FR12G" | "40FR12G" => Ok(SecFormType::FortyFR12G),
            "40-FR12G/A" | "40FR12GA" => Ok(SecFormType::FortyFR12GA),
            "POS EX" => Ok(SecFormType::PosEx),
            "POS 462B" => Ok(SecFormType::Pos462B),
            "POS 462C" => Ok(SecFormType::Pos462C),
            "POS ASR" => Ok(SecFormType::PosAsr),
            "NT 10-K" => Ok(SecFormType::NT10K),
            "NT 10-K/A" | "NT10KA" => Ok(SecFormType::NT10KA),
            "NT 10-Q" => Ok(SecFormType::NT10Q),
            "NT 10-Q/A" | "NT10QA" => Ok(SecFormType::NT10QA),
            "NT 11-K" | "NT11K" => Ok(SecFormType::NT11K),
            "NT15D2" => Ok(SecFormType::NT15D2),
            "25" => Ok(SecFormType::TwentyFive),
            "25/A" => Ok(SecFormType::TwentyFiveA),
            "RW" => Ok(SecFormType::Rw),
            "RW/WD" | "RW/Wd" => Ok(SecFormType::RwWd),
            _ => Err(ValidationError::Invalid(format!(
                "unknown form type: {}",
                s
            ))),
        }
    }
}

pub fn is_valid_filing_type(s: &str) -> bool {
    SecFormType::from_str(s).is_ok()
}

pub enum FilingCategory {
    PeriodicReport,
    CurrentReport,
    ProxyStatement,
    Registration,
    BeneficialOwnership,
    // ...
}

pub enum FilingFrequency {
    Annual,
    Quarterly,
    EventDriven,
    Ongoing,
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
            let f = SecFormType::from_str(s).expect(&format!("from_str failed for {}", s));
            let out = f.to_string();
            assert_eq!(out, s);
        }
    }
}
