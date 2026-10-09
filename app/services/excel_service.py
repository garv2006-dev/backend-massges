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
        # Read Excel file
        try:
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {str(e)}")
        
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
        phone_column = column_mapping.get("phone", "phone")
        
        for idx, row in df.iterrows():
            try:
                # Extract phone number
                phone_raw = str(row.get(phone_column, "")).strip()
                if not phone_raw or phone_raw == "nan":
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
                
                # Extract other fields
                name = str(row.get(column_mapping.get("name", "name"), "")).strip() if column_mapping.get("name") else None
                email = str(row.get(column_mapping.get("email", "email"), "")).strip() if column_mapping.get("email") else None
                language = str(row.get(column_mapping.get("language", "language"), "en")).strip() if column_mapping.get("language") else "en"
                
                # Clean up NaN values
                if name == "nan":
                    name = None
                if email == "nan":
                    email = None
                
                # Create contact
                from app.schemas.contact import ContactCreate
                contact = await self.contact_repo.create(
                    ContactCreate(
                        phone_number=phone_raw,
                        name=name,
                        email=email,
                        language=language
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
            "import_id": contact_import.id,
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
        from app.models.campaign_contact import CampaignContact
        from app.models.contact import Contact
        from app.models.call import Call
        from app.models.transcript import Transcript
        from app.models.extracted_call_result import ExtractedCallResult
        
        # Get campaign contacts with related data
        query = (
            select(CampaignContact, Contact, Call, Transcript, ExtractedCallResult)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .outerjoin(Call, CampaignContact.id == Call.campaign_contact_id)
            .outerjoin(Transcript, Call.id == Transcript.call_id)
            .outerjoin(ExtractedCallResult, Call.id == ExtractedCallResult.call_id)
            .where(CampaignContact.campaign_id == campaign_id)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Prepare data for export
        export_data = []
        for cc, contact, call, transcript, extracted in rows:
            row = {
                "Contact ID": str(contact.id),
                "Name": contact.name or "",
                "Phone Number": contact.phone_number,
                "Email": contact.email or "",
                "Language": contact.language,
                "Campaign Contact Status": cc.status,
                "Retry Count": cc.retry_count,
                "Last Error": cc.last_error or "",
                "Call ID": str(call.id) if call else "",
                "Call Status": call.status if call else "",
                "Call Duration (seconds)": call.duration_seconds if call else "",
                "Call Started": call.started_at.isoformat() if call and call.started_at else "",
                "Call Ended": call.ended_at.isoformat() if call and call.ended_at else "",
                "Failure Reason": call.failure_reason or "" if call else "",
                "AI Interactions": call.ai_interactions if call else 0,
            }
            
            if include_transcripts and transcript:
                row["Transcript"] = transcript.full_transcript or ""
                row["Word Count"] = transcript.word_count
            
            if extracted:
                row["Customer Name"] = extracted.customer_name or ""
                row["Customer Intent"] = extracted.customer_intent or ""
                row["Customer Rating"] = extracted.customer_rating or ""
                row["Complaint"] = extracted.complaint or ""
                row["Follow Up Required"] = extracted.follow_up_required or ""
                row["Follow Up Notes"] = extracted.follow_up_notes or ""
                row["Call Outcome"] = extracted.call_outcome or ""
            
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
