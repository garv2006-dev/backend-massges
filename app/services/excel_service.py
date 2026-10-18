import pandas as pd
import io
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.contact import ContactRepository, ContactImportRepository
from app.utils.phone import normalize_phone_number
import uuid

class ExcelService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.contact_repo = ContactRepository(db)
        self.import_repo = ContactImportRepository(db)

    async def import_contacts(
        self,
        file_content: bytes,
        file_name: str,
        column_mapping: Dict[str, str],
        created_by: Optional[uuid.UUID] = None
    ) -> Tuple[uuid.UUID, Dict[str, Any]]:
        """
        Import contacts from Excel file.
        
        Args:
            file_content: Bytes content of the Excel file
            file_name: Name of the uploaded file
            column_mapping: Mapping of Excel columns to contact fields
                           e.g., {"name": "Name", "phone": "Phone Number", "email": "Email"}
            created_by: User ID who initiated the import
        
        Returns:
            Tuple of (import_id, import_result)
        """
        # Read Excel or CSV file
        try:
            if file_name.lower().endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            else:
                df = pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            raise ValueError(f"Failed to read file: {str(e)}")
        
        # Validate file
        if df.empty:
            raise ValueError("Excel file is empty")
        
        # Create import record
        file_size = len(file_content)
        row_count = len(df)
        
        from app.schemas.contact import ContactImportCreate
        contact_import = await self.import_repo.create(
            ContactImportCreate(
                file_name=file_name,
                file_size=file_size,
                row_count=row_count,
                column_mapping=str(column_mapping)
            ),
            created_by=created_by
        )
        
        # Process rows
        success_count = 0
        failure_count = 0
        duplicate_count = 0
        errors = []
        
        required_fields = ["phone"]
        # Case-insensitive column lookup helper
        col_lookup = {str(c).strip().lower(): str(c) for c in df.columns}
        phone_col = column_mapping.get("phone") or col_lookup.get("phone") or col_lookup.get("phone_number") or col_lookup.get("mobile") or col_lookup.get("contact") or "phone"
        name_col = column_mapping.get("name") or col_lookup.get("name") or col_lookup.get("full_name") or col_lookup.get("first_name")
        email_col = column_mapping.get("email") or col_lookup.get("email") or col_lookup.get("email_address")
        lang_col = column_mapping.get("language") or col_lookup.get("language") or col_lookup.get("lang")
        standard_cols = {c for c in [phone_col, name_col, email_col, lang_col] if c is not None}
        
        for idx, row in df.iterrows():
            try:
                # Extract phone number safely
                raw_val = row.get(phone_col)
                if pd.isna(raw_val) or raw_val is None:
                    phone_raw = ""
                elif isinstance(raw_val, float) and raw_val.is_integer():
                    phone_raw = str(int(raw_val))
                else:
                    phone_raw = str(raw_val).strip()
                    if phone_raw.endswith(".0"):
                        phone_raw = phone_raw[:-2]

                if not phone_raw or phone_raw.lower() in ["nan", "none"]:
                    errors.append(f"Row {idx + 2}: Missing phone number")
                    failure_count += 1
                    continue
                
                # Normalize phone number
                phone_normalized, error = normalize_phone_number(phone_raw)
                if error:
                    errors.append(f"Row {idx + 2}: {error}")
                    failure_count += 1
                    continue
                
                # Check for duplicates
                is_duplicate = await self.contact_repo.check_duplicate(phone_normalized)
                if is_duplicate:
                    duplicate_count += 1
                    continue
                
                # Extract other standard fields
                name = None
                if name_col and not pd.isna(row.get(name_col)):
                    name_val = str(row.get(name_col)).strip()
                    if name_val.lower() not in ["nan", "none", ""]:
                        name = name_val
                
                email = None
                if email_col and not pd.isna(row.get(email_col)):
                    email_val = str(row.get(email_col)).strip()
                    if email_val.lower() not in ["nan", "none", ""]:
                        email = email_val

                language = "en"
                if lang_col and not pd.isna(row.get(lang_col)):
                    lang_val = str(row.get(lang_col)).strip()
                    if lang_val.lower() not in ["nan", "none", ""]:
                        language = lang_val

                # Capture any additional unmapped columns as custom_fields
                custom_fields = {}
                for col in df.columns:
                    if col not in standard_cols and not pd.isna(row.get(col)):
                        custom_fields[str(col)] = row.get(col)
                
                # Create contact
                from app.schemas.contact import ContactCreate
                contact = await self.contact_repo.create(
                    ContactCreate(
                        phone_number=phone_raw,
                        name=name,
                        email=email,
                        language=language,
                        custom_fields=custom_fields if custom_fields else None
                    ),
                    phone_normalized=phone_normalized,
                    import_id=contact_import.id
                )
                success_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                failure_count += 1
        
        # Update import record
        from app.schemas.contact import ContactImportUpdate
        await self.import_repo.update(
            contact_import.id,
            ContactImportUpdate(
                status="completed",
                success_count=success_count,
                failure_count=failure_count,
                duplicate_count=duplicate_count,
                error_message="\n".join(errors[:50]) if errors else None  # Limit error messages
            )
        )
        
        result = {
            "import_id": str(contact_import.id),
            "total_rows": row_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "duplicate_count": duplicate_count,
            "errors": errors[:10]  # Return first 10 errors
        }
        
        return contact_import.id, result

    async def export_campaign_contacts(
        self,
        campaign_id: uuid.UUID,
        include_transcripts: bool = False
    ) -> bytes:
        """
        Export campaign contacts and call results to Excel.
        
        Args:
            campaign_id: Campaign ID to export
            include_transcripts: Whether to include full transcripts
        
        Returns:
            Excel file content as bytes
        """
        from sqlalchemy import select
        from sqlalchemy import select
        from app.models.campaign_contact import CampaignContact
        from app.models.contact import Contact
        from app.models.whatsapp_conversation import WhatsAppConversation
        
        # Get campaign contacts with related data
        query = (
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(CampaignContact.campaign_id == campaign_id)
            .order_by(CampaignContact.created_at.asc())
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Prepare data for export
        export_data = []
        for cc, contact in rows:
            row = {
                "Contact ID": str(contact.id),
                "Name": contact.name or "",
                "Phone Number": contact.phone_number,
                "Email": contact.email or "",
                "Language": contact.language or "en",
                "WhatsApp Delivery Status": cc.status.value if hasattr(cc.status, "value") else str(cc.status or "completed"),
                "Retry Count": cc.retry_count or 0,
                "Dispatched At": cc.started_at.isoformat() if cc.started_at else "",
                "Delivered At": cc.completed_at.isoformat() if cc.completed_at else "",
                "Last Error": cc.last_error or "",
            }
            export_data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Escape formula-leading values
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(
                    lambda x: f"'{x}" if isinstance(x, str) and x.startswith(('=', '+', '-', '@')) else x
                )
        
        # Write to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Campaign Results')
        
        output.seek(0)
        return output.getvalue()
